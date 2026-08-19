#!/usr/bin/env python3
"""Real released rill-pm-adapter RUNTIME + pm-rill-shadow v1 protocol roundtrip.

This is NOT a mock and NOT a Core mirror.  It is a minimal protocol client that
talks to a REAL released `rill-pm-adapter` binary over its unix socket and fills
the real runtime verdicts that the wire harness deliberately leaves BLOCKED:

  executableVerdict  -- the exact released adapter runs (`--version`)
  versionVerdict     -- `--version` reports the adapter crate version (0.15.0)
  startupVerdict     -- the adapter has published a connectable unix socket
  statusVerdict      -- real status roundtrip (contract/protocol/requestId echo/
                        rillVersion/adapterVersion/capabilities/modelHealth)
  observeVerdict     -- real observe decision+recommendation roundtrip
  outcomeVerdict     -- real validated outcome roundtrip using the REAL
                        decisionId/actionId/contextKey/goal from the observe above
  failClosedVerdict  -- real negative suite: every mismatch is rejected by the
                        REAL adapter with its frozen error codes (never silently
                        accepted, never a self-invented mock contract)

Protocol source of truth: pinned Rill v1.2.0
  crates/rill-pm-adapter/src/lib.rs  (Request/Response envelopes, error codes,
                                      observe/outcome ledger semantics)
  crates/rill-pm-adapter/src/main.rs (NDJSON framing, oversized-frame fail-closed)

Every positive verdict requires an actual `ok:true` envelope with the requestId
echoed back and the real upstream wire fields verified (rillVersion/adapterVersion
for status, decisionId+recommendation for observe, accepted for outcome).  A peer
close, timeout, error envelope or a successful-looking-but-wrong response is
NEVER a PASS.  Any release-critical verdict that is not PASS makes this job exit
non-zero (BLOCKED included): there is no "BLOCKED + green workflow" path.

Usage:
  python3 scripts/rill_adapter_runtime.py \
    --adapter <path/to/rill-pm-adapter-1.2.0-linux-x86_64-musl> \
    --socket /run/pm-rill.sock \
    --state-dir <dir> --out-dir docs
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'contracts/rill-ipc.schema.json').read_text())
RESP_SCHEMA = json.loads((ROOT / 'contracts/rill-ipc-response.schema.json').read_text())
DEP = json.loads((ROOT / 'contracts/rill-dependency.json').read_text())

# Expected wire identity, driven by the pinned dependency contract (never
# hardcoded elsewhere).  Three distinct versions: release bundle 1.2.0, adapter
# crate/binary 0.15.0 (Preview), pm-rill-shadow protocol v1.
EXPECTED_RELEASE = (DEP.get('upstream') or {}).get('releaseVersion', '1.2.0')
EXPECTED_ADAPTER = (DEP.get('upstream', {}).get('adapter') or {}).get('adapterVersion', '0.15.0')
CONTRACT = (DEP.get('protocol') or {}).get('contract', 'pm-rill-shadow')
PROTOCOL = (DEP.get('protocol') or {}).get('protocolVersion', 1)
REQUIRED_CAPS = list((DEP.get('capabilities') or {}).get('required', []))
MAX_REQUEST_ID_LEN = 128

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

HEXDIGITS = set('0123456789abcdefABCDEF')


def frame(obj):
    return json.dumps(obj, separators=(',', ':')).encode() + b'\n'


class AdapterBus:
    """Newline-framed JSON client over the REAL adapter unix socket.

    One connection per request for clean isolation (the adapter serves each
    connection until EOF or an oversized frame).  Returns a structured result so
    a silent close / timeout / oversized response is never mistaken for a PASS.
    """

    def __init__(self, sock_path, timeout=3.0, max_read=1 << 20):
        self.sock_path = sock_path
        self.timeout = timeout
        self.max_read = max_read
        self.s = None

    def connect(self):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(self.timeout)
        self.s.connect(self.sock_path)

    def close(self):
        if self.s is not None:
            try:
                self.s.close()
            except Exception:  # noqa: BLE001
                pass
            self.s = None

    def _recv_frame(self):
        data = b''
        while True:
            try:
                chunk = self.s.recv(65536)
            except socket.timeout:
                return ('timeout', data)
            except OSError:
                return ('error', data)
            if not chunk:
                return ('eof', data)
            data += chunk
            if b'\n' in data:
                return ('ok', data)
            if len(data) > self.max_read:
                return ('oversize', data)

    def exchange(self, payload):
        """Send one NDJSON request, read one response, close the connection."""
        self.connect()
        try:
            self.s.sendall(frame(payload))
        except OSError:
            self.close()
            return {'status': 'send-error', 'resp': None, 'closed': True, 'note': 'send failed'}
        status, raw = self._recv_frame()
        self.close()
        if status == 'ok':
            line = raw.split(b'\n', 1)[0]
            try:
                resp = json.loads(line)
                return {'status': 'ok', 'resp': resp, 'closed': False, 'note': ''}
            except json.JSONDecodeError:
                return {'status': 'malformed', 'resp': None, 'closed': False,
                        'note': line[:200].decode(errors='replace')}
        if status == 'eof':
            return {'status': 'eof', 'resp': None, 'closed': True, 'note': 'peer closed, no response'}
        if status == 'timeout':
            return {'status': 'timeout', 'resp': None, 'closed': False, 'note': 'recv timeout'}
        if status == 'error':
            return {'status': 'conn-error', 'resp': None, 'closed': True, 'note': 'connection error'}
        if status == 'oversize':
            return {'status': 'oversize', 'resp': None, 'closed': True, 'note': 'unbounded response'}
        return {'status': status, 'resp': None, 'closed': False, 'note': ''}

    def send_raw(self, raw_bytes):
        """Send raw bytes (malformed / oversized / truncated frames) and read the
        adapter's reaction.  The adapter closes the connection on an oversized
        frame without parsing it (fail-closed), so a close here is expected."""
        self.connect()
        try:
            self.s.sendall(raw_bytes)
        except OSError:
            self.close()
            return {'status': 'send-error', 'resp': None, 'closed': True, 'note': 'send failed (peer closed)'}
        status, raw = self._recv_frame()
        self.close()
        if status == 'ok':
            line = raw.split(b'\n', 1)[0]
            try:
                return {'status': 'ok', 'resp': json.loads(line), 'closed': False, 'note': ''}
            except json.JSONDecodeError:
                return {'status': 'malformed', 'resp': None, 'closed': False, 'note': 'non-json'}
        if status == 'eof':
            return {'status': 'eof', 'resp': None, 'closed': True, 'note': 'peer closed, no response'}
        if status == 'timeout':
            return {'status': 'timeout', 'resp': None, 'closed': False, 'note': 'recv timeout'}
        if status == 'error':
            return {'status': 'conn-error', 'resp': None, 'closed': True, 'note': 'connection error'}
        return {'status': status, 'resp': None, 'closed': False, 'note': ''}


# ---------------------------------------------------------------------------
# Positive roundtrip gates (all must be real ok:true envelopes)
# ---------------------------------------------------------------------------

def check_ok_envelope(res, request_id):
    """Uniform response envelope + requestId echo.  Any transport problem, peer
    close, timeout, missing/mismatched contract/protocol/requestId or ok!=true
    fails the gate."""
    if res['status'] != 'ok':
        return (False, f"transport {res['status']} ({res.get('note', '')})")
    resp = res['resp']
    if not isinstance(resp, dict):
        return (False, 'non-object response')
    if resp.get('contract') != CONTRACT:
        return (False, f"contract={resp.get('contract')!r}")
    if resp.get('protocolVersion') != PROTOCOL:
        return (False, f"protocolVersion={resp.get('protocolVersion')!r}")
    if resp.get('requestId') != request_id:
        return (False, f"requestId echo {resp.get('requestId')!r} != {request_id!r}")
    if resp.get('ok') is not True:
        err = resp.get('error') or {}
        return (False, f"ok={resp.get('ok')!r} error={err.get('code')}:{err.get('message')}")
    return (True, 'ok')


def status_gate(res, request_id):
    ok, reason = check_ok_envelope(res, request_id)
    if not ok:
        return (False, reason)
    resp = res['resp']
    # Real wire fields: rillVersion (1.2.0) and adapterVersion (0.15.0).
    if resp.get('rillVersion') != EXPECTED_RELEASE:
        return (False, f"rillVersion={resp.get('rillVersion')!r} != {EXPECTED_RELEASE}")
    if resp.get('adapterVersion') != EXPECTED_ADAPTER:
        return (False, f"adapterVersion={resp.get('adapterVersion')!r} != {EXPECTED_ADAPTER}")
    if resp.get('state') not in ('collecting', 'learning'):
        return (False, f"state={resp.get('state')!r}")
    caps = resp.get('capabilities') or []
    missing = [c for c in REQUIRED_CAPS if c not in caps]
    if missing:
        return (False, f"missing required capabilities: {','.join(missing)}")
    mh = resp.get('modelHealth') or {}
    if mh.get('overall') != 'healthy':
        return (False, f"modelHealth.overall={mh.get('overall')!r}")
    return (True, 'ok')


def observe_gate(res, request_id, available_ids):
    ok, reason = check_ok_envelope(res, request_id)
    if not ok:
        return (False, reason)
    resp = res['resp']
    decision_id = resp.get('decisionId')
    if not isinstance(decision_id, str) or not decision_id or len(decision_id) > 64 \
            or not all(c in HEXDIGITS for c in decision_id):
        return (False, f"decisionId invalid: {decision_id!r}")
    rec = resp.get('recommendation') or {}
    action_id = rec.get('actionId')
    if action_id not in available_ids:
        return (False, f"recommendation.actionId={action_id!r} not in availableActions")
    if rec.get('advisory') is not True:
        return (False, f"recommendation.advisory={rec.get('advisory')!r}")
    conf = rec.get('confidence')
    if not isinstance(conf, (int, float)) or not (0.0 <= conf <= 1.0):
        return (False, f"recommendation.confidence={conf!r}")
    return (True, f"decisionId={decision_id} actionId={action_id} confidence={conf}")


def outcome_gate(res, request_id):
    ok, reason = check_ok_envelope(res, request_id)
    if not ok:
        return (False, reason)
    if res['resp'].get('accepted') is not True:
        return (False, f"accepted={res['resp'].get('accepted')!r}")
    return (True, 'ok')


# ---------------------------------------------------------------------------
# Real negative suite (verdicts against the REAL adapter's frozen error codes)
# ---------------------------------------------------------------------------

def reject_gate(res, expect_code):
    """A negative case is a PASS only when the adapter rejected it with the
    exact frozen upstream code (or, for oversized frames, closed the connection
    without responding).  An ok:true (silent acceptance) is always a FAIL."""
    if res['status'] == 'ok':
        resp = res['resp']
        if isinstance(resp, dict) and resp.get('ok') is True:
            return (False, f"adapter SILENTLY ACCEPTED: {json.dumps(resp)[:200]}")
        code = (resp.get('error') or {}).get('code') if isinstance(resp, dict) else None
        if code == expect_code:
            return (True, f"rejected with {code}")
        return (False, f"rejected with {code!r} (expected {expect_code})")
    # Transport-level fail-closed is expected only for the oversized-frame case.
    if expect_code == 'close' and res['status'] in ('eof', 'conn-error', 'send-error'):
        return (True, f"fail-closed: connection closed, nothing parsed ({res['status']})")
    if expect_code == 'close':
        return (False, f"oversized frame: unexpected transport {res['status']}")
    # A syntactically incomplete frame without a trailing newline is not a
    # complete NDJSON request.  The upstream adapter must therefore wait for
    # the rest of the frame; the client-side deadline proves a bounded,
    # fail-closed outcome.  It would be incorrect to require invalidJson before
    # the frame terminator has arrived.
    if expect_code == 'incomplete-frame':
        if res['status'] in ('timeout', 'eof', 'conn-error'):
            return (True, f"fail-closed incomplete frame ({res['status']}); no response accepted")
        return (False, f"incomplete frame produced unexpected result {res['status']}")
    # Any other transport problem for a code-expecting negative is a FAIL (the
    # adapter must answer, not vanish, for non-oversized requests).
    return (False, f"transport {res['status']} ({res.get('note', '')})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def record(log, name, verdict, detail=''):
    log.append({'name': name, 'verdict': verdict, 'detail': detail})
    print(f'{verdict}  {name}' + (f'  ({detail})' if detail else ''))


def fresh_observe(bus, request_id, state_dir, context_key, goal):
    """Send one real observe and return its binding (decisionId/actionId/...)."""
    payload = {
        'contract': CONTRACT, 'protocolVersion': PROTOCOL, 'requestId': request_id, 'op': 'observe',
        'deviceProfile': 'recommended', 'capabilityHash': 'cap-hash', 'topologyGeneration': 1,
        'pathId': 'path:lan-to-wan', 'routeIdentity': 'unresolved',
        'workloadClass': ['plain_forwarding'], 'measurementClass': 'controlled_ab',
        'context': {}, 'integrations': [], 'goal': goal,
        'integrationFingerprint': 'integ-fp', 'contextKey': context_key,
        'availableActions': [{'id': 'network.backlog'}],
    }
    if jsonschema is not None:
        jsonschema.Draft202012Validator(SCHEMA).validate(payload)
    res = bus.exchange(payload)
    ok, reason = observe_gate(res, request_id, ['network.backlog'])
    if not ok:
        return None, (False, reason), res, payload
    resp = res['resp']
    binding = {
        'decisionId': resp['decisionId'],
        'actionId': resp['recommendation']['actionId'],
        'contextKey': context_key, 'goal': goal, 'modelGeneration': 1,
    }
    return binding, (True, reason), res, payload


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--adapter', required=True, help='path to the released rill-pm-adapter binary')
    ap.add_argument('--socket', required=True, help='unix socket path of the running adapter')
    ap.add_argument('--state-dir', default='/etc/performance-manager/rill')
    ap.add_argument('--out-dir', default=str(ROOT.parent / 'docs'))
    args = ap.parse_args(argv)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    log = []

    rt = {k: 'BLOCKED' for k in
          ('executableVerdict', 'versionVerdict', 'startupVerdict', 'statusVerdict',
           'observeVerdict', 'outcomeVerdict', 'failClosedVerdict', 'pmCoreRoundtripVerdict')}
    negative_results = []
    roundtrip = {'contract': CONTRACT, 'protocolVersion': PROTOCOL,
                 'releaseVersion': EXPECTED_RELEASE, 'adapterVersion': EXPECTED_ADAPTER,
                 'positive': [], 'negative': [], 'persistence': None}

    adapter = Path(args.adapter)

    # 1. Executable + version of the EXACT released artifact.
    if not adapter.exists() or not os_access(adapter):
        rt['executableVerdict'] = 'FAIL'
        record(log, 'adapter executable present', rt['executableVerdict'],
               f'{adapter} missing or not executable (explicit path must run)')
    else:
        vp = subprocess.run([str(adapter), '--version'], capture_output=True, text=True, timeout=20)
        rt['executableVerdict'] = 'PASS' if vp.returncode == 0 else 'FAIL'
        record(log, 'adapter executable runs (--version)', rt['executableVerdict'],
               f"rc={vp.returncode}" + ('' if vp.returncode == 0 else f" out={vp.stdout.strip()[:120]} err={vp.stderr.strip()[:120]}"))
        combined = (vp.stdout + vp.stderr)
        if vp.returncode == 0:
            # Adapter crate/binary version is 0.15.0 (Preview), NOT the release 1.2.0.
            rt['versionVerdict'] = 'PASS' if EXPECTED_ADAPTER in combined else 'FAIL'
            record(log, f'adapter --version reports {EXPECTED_ADAPTER}', rt['versionVerdict'],
                   ''.join(combined.splitlines())[:160])
            if EXPECTED_RELEASE in combined and EXPECTED_ADAPTER in combined:
                record(log, f'release {EXPECTED_RELEASE} and adapter {EXPECTED_ADAPTER} not conflated in --version', 'INFO')
        else:
            rt['versionVerdict'] = 'FAIL'
            record(log, f'adapter --version reports {EXPECTED_ADAPTER}', 'FAIL', '--version failed')
        (out_dir / 'rill-adapter-version.txt').write_text(combined.strip() + '\n')
        (out_dir / 'rill-adapter-runtime.log').write_text('\n'.join(json.dumps(x, ensure_ascii=False) for x in log) + '\n')

    # 2. Startup: verify the already-launched adapter published a connectable socket.
    sock_path = args.socket
    bus = AdapterBus(sock_path)
    deadline = time.time() + 10
    connected = False
    while time.time() < deadline:
        try:
            bus.connect()
            connected = True
            bus.close()
            break
        except OSError:
            time.sleep(0.5)
    rt['startupVerdict'] = 'PASS' if connected else 'BLOCKED'
    record(log, 'adapter unix socket connectable', rt['startupVerdict'], sock_path)

    if not connected:
        rt['statusVerdict'] = rt['observeVerdict'] = rt['outcomeVerdict'] = rt['failClosedVerdict'] = 'BLOCKED'
    else:
        # 3. Real status roundtrip.
        try:
            res = bus.exchange({'contract': CONTRACT, 'protocolVersion': PROTOCOL,
                                'requestId': 'ci-status-1', 'op': 'status'})
            ok, reason = status_gate(res, 'ci-status-1')
            rt['statusVerdict'] = 'PASS' if ok else 'FAIL'
            record(log, 'status roundtrip (contract/protocol/requestId/rillVersion/caps/health)', rt['statusVerdict'], reason)
            roundtrip['positive'].append({'op': 'status', 'ok': ok, 'reason': reason, 'response': res.get('resp')})
        except Exception as e:  # noqa: BLE001
            rt['statusVerdict'] = 'FAIL'
            record(log, 'status roundtrip', 'FAIL', str(e))

        # 4. Real observe -> captures the REAL decision binding.
        binding = None
        try:
            binding, (ok, reason), res, _ = fresh_observe(
                bus, 'ci-observe-1', args.state_dir,
                'ctx-v1:profile=recommended;cap=cap-hash;topo=1;path=path:lan-to-wan;route=unresolved;workload=p;integ=integ-fp;goal=balanced',
                'balanced')
            rt['observeVerdict'] = 'PASS' if ok else 'FAIL'
            record(log, 'observe roundtrip (goal + integrations array + real decision)', rt['observeVerdict'], reason)
            roundtrip['positive'].append({'op': 'observe', 'ok': ok, 'reason': reason,
                                          'request': res.get('resp') and 'sent'})
        except Exception as e:  # noqa: BLE001
            rt['observeVerdict'] = 'FAIL'
            record(log, 'observe roundtrip', 'FAIL', str(e))

        # 5. Real validated outcome using the REAL observe binding (frozen
        #    contextKey/goal/actionId + real decisionId).  No fabricated values.
        try:
            if binding is None:
                rt['outcomeVerdict'] = 'FAIL'
                record(log, 'validated outcome roundtrip (bound decision)', 'FAIL', 'no real decision binding (observe failed)')
            else:
                outcome_req = {
                    'contract': CONTRACT, 'protocolVersion': PROTOCOL, 'requestId': 'ci-outcome-1', 'op': 'outcome',
                    'decisionId': binding['decisionId'], 'contextKey': binding['contextKey'],
                    'actionId': binding['actionId'], 'sessionId': 'ci-session-1', 'goal': binding['goal'],
                    'modelGeneration': binding['modelGeneration'], 'validated': True, 'reward': 0.0,
                }
                if jsonschema is not None:
                    jsonschema.Draft202012Validator(SCHEMA).validate(outcome_req)
                res = bus.exchange(outcome_req)
                ok, reason = outcome_gate(res, 'ci-outcome-1')
                rt['outcomeVerdict'] = 'PASS' if ok else 'FAIL'
                record(log, f"validated outcome roundtrip (decisionId={binding['decisionId'][:12]}…) accepted={res.get('resp') and res['resp'].get('accepted')}", rt['outcomeVerdict'], reason)
                roundtrip['positive'].append({'op': 'outcome', 'ok': ok, 'reason': reason,
                                              'decisionId': binding['decisionId'], 'response': res.get('resp')})
        except Exception as e:  # noqa: BLE001
            rt['outcomeVerdict'] = 'FAIL'
            record(log, 'validated outcome roundtrip', 'FAIL', str(e))

        # 6. Real negative suite (per rc.7 prompt section 23) against the REAL
        #    adapter's frozen error codes.
        def neg(name, expect_code, res):
            ok, reason = reject_gate(res, expect_code)
            negative_results.append({'name': name, 'ok': ok, 'reason': reason,
                                     'response': res.get('resp')})
            record(log, f'negative: {name}', 'PASS' if ok else 'FAIL', reason)

        # Static rejects (no decision needed).
        neg('wrong-contract', 'wrongContract', bus.exchange({
            'contract': 'pm-rill-other', 'protocolVersion': PROTOCOL, 'requestId': 'ci-neg-1', 'op': 'status'}))
        neg('foreign-protocol-version', 'wrongProtocolVersion', bus.exchange({
            'contract': CONTRACT, 'protocolVersion': 2, 'requestId': 'ci-neg-2', 'op': 'status'}))
        neg('empty-request-id', 'invalidRequestId', bus.exchange({
            'contract': CONTRACT, 'protocolVersion': PROTOCOL, 'requestId': '', 'op': 'status'}))
        # Observe missing required goal -> serde invalidRequest (goal is required).
        neg('observe-missing-goal', 'invalidRequest', bus.exchange({
            'contract': CONTRACT, 'protocolVersion': PROTOCOL, 'requestId': 'ci-neg-3', 'op': 'observe',
            'deviceProfile': 'recommended', 'capabilityHash': 'h', 'topologyGeneration': 1,
            'pathId': 'path:lan-to-wan', 'routeIdentity': 'r', 'workloadClass': ['plain_forwarding'],
            'measurementClass': 'controlled_ab', 'context': {}, 'integrations': [],
            'integrationFingerprint': 'x', 'contextKey': 'ctx-v1:goal=balanced',
            'availableActions': [{'id': 'network.backlog'}]}))
        # Observe integrations as OBJECT instead of array -> serde invalidRequest.
        neg('observe-integrations-object', 'invalidRequest', bus.exchange({
            'contract': CONTRACT, 'protocolVersion': PROTOCOL, 'requestId': 'ci-neg-4', 'op': 'observe',
            'deviceProfile': 'recommended', 'capabilityHash': 'h', 'topologyGeneration': 1,
            'pathId': 'path:lan-to-wan', 'routeIdentity': 'r', 'workloadClass': ['plain_forwarding'],
            'measurementClass': 'controlled_ab', 'context': {}, 'integrations': {}, 'goal': 'balanced',
            'integrationFingerprint': 'x', 'contextKey': 'ctx-v1:goal=balanced',
            'availableActions': [{'id': 'network.backlog'}]}))
        # Outcome carrying an upstream-unknown field -> deny_unknown_fields reject.
        neg('outcome-unknown-field', 'invalidRequest', bus.exchange({
            'contract': CONTRACT, 'protocolVersion': PROTOCOL, 'requestId': 'ci-neg-5', 'op': 'outcome',
            'decisionId': 'deadbeef', 'contextKey': 'ctx-v1:goal=balanced', 'actionId': 'network.backlog',
            'sessionId': 's', 'goal': 'balanced', 'modelGeneration': 1, 'validated': True, 'reward': 0.0,
            'measurementClass': 'controlled_ab'}))
        # Unknown (but well-formed) decisionId -> unknownDecision.
        neg('unknown-decision', 'unknownDecision', bus.exchange({
            'contract': CONTRACT, 'protocolVersion': PROTOCOL, 'requestId': 'ci-neg-6', 'op': 'outcome',
            'decisionId': 'deadbeef', 'contextKey': 'ctx-v1:goal=balanced', 'actionId': 'network.backlog',
            'sessionId': 's', 'goal': 'balanced', 'modelGeneration': 1, 'validated': True, 'reward': 0.0}))
        # validated=false -> nonValidated (rejected before any ledger mutation).
        neg('validated-false', 'nonValidated', bus.exchange({
            'contract': CONTRACT, 'protocolVersion': PROTOCOL, 'requestId': 'ci-neg-7', 'op': 'outcome',
            'decisionId': 'deadbeef', 'contextKey': 'ctx-v1:goal=balanced', 'actionId': 'network.backlog',
            'sessionId': 's', 'goal': 'balanced', 'modelGeneration': 1, 'validated': False, 'reward': 0.0}))
        # Oversized frame -> the adapter closes the connection without parsing.
        oversized = b'x' * 65537 + b'\n'  # > --max-message 65536 used by CI
        neg('oversized-frame', 'close', bus.send_raw(oversized))
        # A newline-terminated malformed frame is invalidJson.  A truncated
        # frame without its NDJSON terminator is incomplete input, so the
        # bounded client timeout/close is the correct fail-closed behavior.
        neg('malformed-json', 'invalidJson', bus.send_raw(b'{not-json\n'))
        neg('truncated-json', 'incomplete-frame', bus.send_raw(b'{"contract":"pm-rill-shadow"'))

        # Decision-bound rejects need a REAL pending decision (fresh observe).
        neg_binding = None
        try:
            neg_binding, (ok, _), _, _ = fresh_observe(
                bus, 'ci-neg-obs-1', args.state_dir,
                'ctx-v1:profile=recommended;cap=cap-hash;topo=1;path=path:lan-to-wan;route=unresolved;workload=p;integ=integ-fp;goal=balanced',
                'balanced')
            if not ok:
                raise RuntimeError('baseline observe for negatives failed')
        except Exception as e:  # noqa: BLE001
            record(log, 'negative baseline observe', 'FAIL', str(e))
            neg_binding = None

        def bound_outcome(request_id, **overrides):
            req = {
                'contract': CONTRACT, 'protocolVersion': PROTOCOL, 'requestId': request_id, 'op': 'outcome',
                'decisionId': neg_binding['decisionId'], 'contextKey': neg_binding['contextKey'],
                'actionId': neg_binding['actionId'], 'sessionId': 'ci-neg-session', 'goal': neg_binding['goal'],
                'modelGeneration': neg_binding['modelGeneration'], 'validated': True, 'reward': 0.0,
            }
            req.update(overrides)
            return req

        if neg_binding is not None:
            neg('outcome-action-mismatch', 'actionMismatch', bus.exchange(
                bound_outcome('ci-neg-8', actionId='no.such.action')))
            neg('outcome-context-mismatch', 'contextMismatch', bus.exchange(
                bound_outcome('ci-neg-9', contextKey='ctx-v1:goal=other')))
            neg('outcome-generation-mismatch', 'generationMismatch', bus.exchange(
                bound_outcome('ci-neg-10', modelGeneration=99)))
            # Duplicate: first outcome for this real decision is ACCEPTED, the
            # second identical one must be rejected with duplicateFeedback.
            first = bus.exchange(bound_outcome('ci-neg-dup-1'))
            if first['status'] == 'ok' and isinstance(first['resp'], dict) and first['resp'].get('ok') is True \
                    and first['resp'].get('accepted') is True:
                roundtrip['positive'].append({'op': 'outcome', 'ok': True, 'reason': 'duplicate-test first accepted',
                                              'decisionId': neg_binding['decisionId']})
                neg('outcome-duplicate', 'duplicateFeedback', bus.exchange(bound_outcome('ci-neg-dup-2')))
            else:
                record(log, 'negative: outcome-duplicate', 'FAIL', 'first outcome was not accepted')
                negative_results.append({'name': 'outcome-duplicate', 'ok': False,
                                         'reason': 'prerequisite accepted outcome failed', 'response': first.get('resp')})
        else:
            for name in ('outcome-action-mismatch', 'outcome-context-mismatch',
                         'outcome-generation-mismatch', 'outcome-duplicate'):
                negative_results.append({'name': name, 'ok': False, 'reason': 'no real decision binding available'})
                record(log, f'negative: {name}', 'FAIL', 'no real decision binding available')

        rt['failClosedVerdict'] = ('PASS' if (negative_results and all(n['ok'] for n in negative_results))
                                   else ('FAIL' if any(n['ok'] is False for n in negative_results) else 'BLOCKED'))
        record(log, f'negative suite ({len(negative_results)} cases)', rt['failClosedVerdict'],
               'all rejected' if rt['failClosedVerdict'] == 'PASS' else 'one or more accepted/rejected-wrong')
        roundtrip['negative'] = negative_results

        # Persistence sanity: the real adapter persists state after observe/outcome.
        try:
            state_file = Path(args.state_dir) / 'adapter-state.json'
            if state_file.exists():
                st = json.loads(state_file.read_text())
                pers_ok = (st.get('schemaVersion') == 1 and st.get('adapterVersion') == EXPECTED_ADAPTER
                           and st.get('modelGeneration') == 1)
                roundtrip['persistence'] = {
                    'status': 'PASS' if pers_ok else 'FAIL',
                    'path': str(state_file),
                    'auditedModelGeneration': st.get('modelGeneration'),
                    'expectedModelGeneration': 1,
                }
                record(log, 'adapter persisted state (adapter-state.json)', 'PASS' if pers_ok else 'FAIL', str(state_file))
            else:
                roundtrip['persistence'] = {'status': 'BLOCKED', 'path': str(state_file), 'note': 'no state file found'}
                record(log, 'adapter persisted state (adapter-state.json)', 'BLOCKED', 'no state file found')
        except Exception as e:  # noqa: BLE001
            roundtrip['persistence'] = {'status': 'FAIL', 'note': str(e)}
            record(log, 'adapter persisted state (adapter-state.json)', 'FAIL', str(e))

        (out_dir / 'rill-protocol-roundtrip.json').write_text(
            json.dumps(roundtrip, ensure_ascii=False, indent=2) + '\n')
        bus.close()

    # 7. Release-critical verdicts: any non-PASS (FAIL or BLOCKED) is a non-zero exit.
    critical = ['executableVerdict', 'versionVerdict', 'startupVerdict', 'statusVerdict',
                'observeVerdict', 'outcomeVerdict', 'failClosedVerdict']
    runtime_compat = ['executableVerdict', 'versionVerdict', 'startupVerdict', 'statusVerdict']
    functional = ['observeVerdict', 'outcomeVerdict', 'failClosedVerdict']
    if all(rt[k] == 'PASS' for k in critical):
        overall = 'PASS'
    elif any(rt[k] == 'FAIL' for k in critical):
        overall = 'FAIL'
    else:
        overall = 'BLOCKED'

    def _combine(names):
        vals = [rt[k] for k in names]
        if any(v == 'FAIL' for v in vals):
            return 'FAIL'
        if all(v == 'PASS' for v in vals):
            return 'PASS'
        return 'BLOCKED'

    # Per-job evidence (never a shared parallel-overwritten JSON): this job owns
    # ONLY docs/rill-runtime.json.  The final aggregator merges per-job files by
    # PM commit SHA.
    def _pm_commit():
        try:
            return subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                  capture_output=True, text=True).stdout.strip() or 'unknown'
        except Exception:  # noqa: BLE001
            return 'unknown'

    rt['pmCoreRoundtripVerdict'] = 'BLOCKED'  # filled by pm-core-rill-roundtrip
    runtime_evidence = {
        'schemaVersion': 2,
        'contract': 'pm<->rill-runtime',
        'protocolContract': CONTRACT,
        'protocolVersion': PROTOCOL,
        'pmVersion': (ROOT / 'VERSION').read_text().strip(),
        'pmCommitSha': os.environ.get('GITHUB_SHA', None) or _pm_commit(),
        'adapterBinary': str(adapter),
        'adapterSha256': hashlib.sha256(adapter.read_bytes()).hexdigest() if adapter.is_file() else None,
        'adapterSocket': sock_path,
        'adapterStateDir': args.state_dir,
        'releaseVersion': EXPECTED_RELEASE,
        'adapterVersion': EXPECTED_ADAPTER,
        'runtimeCompatibilityVerdict': _combine(runtime_compat),
        'functionalIntegrationVerdict': _combine(functional),
        'verdicts': rt,
        'overallVerdict': overall,
        'exitCodePolicy': 'non-zero on any verdict that is not PASS (BLOCKED included); no BLOCKED+green path',
        'note': 'Real released adapter runtime + pm-rill-shadow v1 protocol roundtrip inside the OpenWrt rootfs. '
                'All positive verdicts require real ok:true envelopes with requestId echo and the real upstream '
                'wire fields (rillVersion/adapterVersion, decisionId+recommendation, accepted). Negative cases are '
                'judged against the REAL adapter\'s frozen error codes. Peer close/timeout never fakes PASS.',
    }
    (out_dir / 'rill-runtime.json').write_text(json.dumps(runtime_evidence, ensure_ascii=False, indent=2) + '\n')

    print('runtime evidence ->', out_dir / 'rill-runtime.json')

    if overall != 'PASS':
        print(f'FINAL: runtime overall={overall}; release-critical job must FAIL')
        return 1
    print('FINAL: runtime overall=PASS')
    return 0


def os_access(p: Path) -> bool:
    try:
        return p.is_file() and (p.stat().st_mode & 0o111) != 0
    except OSError:
        return False


if __name__ == '__main__':
    sys.exit(main())
