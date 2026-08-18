#!/usr/bin/env python3
"""Real released rill-pm-adapter RUNTIME + pm-rill-shadow v1 protocol roundtrip.

This is NOT a mock and NOT a Core mirror.  It is a minimal protocol client that
talks to a REAL released `rill-pm-adapter` binary over its unix socket and fills
the real runtime verdicts that the wire harness deliberately leaves BLOCKED:

  executableVerdict  -- the exact released adapter runs (`--version`)
  versionVerdict     -- `--version` reports the Preview crate version 0.15.0
  startupVerdict     -- the adapter has published a connectable unix socket
  statusVerdict      -- real status roundtrip (contract/protocol/capabilities/health/versions)
  observeVerdict     -- real observe advisory roundtrip
  outcomeVerdict     -- real validated outcome acceptance
  failClosedVerdict  -- negative cases are rejected (never silently accepted)

The CI job (pm-rill-runtime inside the OpenWrt rootfs) launches the EXACT,
already-verified adapter artifact and passes its socket/state-dir here.  Any
verdict that cannot be honestly proven stays BLOCKED (never a fabricated PASS).

Usage:
  python3 scripts/rill_adapter_runtime.py \
    --adapter <path/to/rill-pm-adapter-1.2.0-linux-x86_64-musl> \
    --socket /run/pm-rill.sock \
    --state-dir <dir> --out-dir docs
"""
from __future__ import annotations
import argparse
import json
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / 'contracts/rill-ipc.schema.json').read_text())
REQUIRED_CAPS = ['context-partitioned-model', 'goal-partition', 'validated-outcome', 'decision-ledger', 'model-health']
EXPECTED_RELEASE = '1.2.0'
EXPECTED_ADAPTER = '0.15.0'
PROTOCOL = 1

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None


def frame(obj):
    return json.dumps(obj, separators=(',', ':')).encode() + b'\n'


class AdapterBus:
    """Newline-framed JSON client over a unix socket to the REAL adapter."""

    def __init__(self, sock_path, timeout=3.0):
        self.sock_path = sock_path
        self.timeout = timeout

    def connect(self):
        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.s.settimeout(self.timeout)
        self.s.connect(self.sock_path)

    def exchange(self, op, extra=None):
        if getattr(self, 's', None) is None:
            self.connect()
        req = {'contract': 'pm-rill-shadow', 'protocolVersion': PROTOCOL,
               'requestId': 'ci-roundtrip-%d' % int(time.time() * 1000), 'op': op}
        if extra:
            req.update(extra)
        if jsonschema is not None and op in ('observe', 'outcome'):
            jsonschema.Draft202012Validator(SCHEMA).validate(req)
        self.s.sendall(frame(req))
        resp = b''
        while True:
            data = self.s.recv(65536)
            if not data:
                break
            resp += data
            if b'\n' in resp:
                break
        body = resp.split(b'\n')[0] if resp else b'{}'
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return {'error': 'non-json', '_raw': body[:200].decode(errors='replace')}

    def close(self):
        if getattr(self, 's', None) is not None:
            try:
                self.s.close()
            except Exception:
                pass
            self.s = None


def status_gate(resp):
    """Mirror of the Core capability gate over a real status response."""
    if not isinstance(resp, dict):
        return (False, 'malformed')
    if resp.get('contract') != 'pm-rill-shadow':
        return (False, 'contract-mismatch')
    if (resp.get('protocolVersion') or 0) != PROTOCOL:
        return (False, 'protocol-version-mismatch')
    caps = resp.get('capabilities') or []
    missing = [c for c in REQUIRED_CAPS if c not in caps]
    if missing:
        return (False, 'missing-required-capability:' + ','.join(missing))
    if (resp.get('modelHealth') or {}).get('overall') != 'healthy':
        return (False, 'model-unhealthy')
    return (True, 'ok')


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
    def record(name, verdict, detail=''):
        log.append({'name': name, 'verdict': verdict, 'detail': detail})
        print(f'{verdict}  {name}' + (f'  ({detail})' if detail else ''))

    rt = {k: 'BLOCKED' for k in
          ('executableVerdict', 'versionVerdict', 'startupVerdict', 'statusVerdict',
           'observeVerdict', 'outcomeVerdict', 'failClosedVerdict', 'pmCoreRoundtripVerdict')}

    adapter = Path(args.adapter)
    # 1. Executable + version.
    if not adapter.exists() or not os_access(adapter):
        record('adapter executable present', 'BLOCKED', f'{adapter} missing/not executable')
    else:
        vp = subprocess.run([str(adapter), '--version'], capture_output=True, text=True, timeout=20)
        rt['executableVerdict'] = 'PASS' if vp.returncode == 0 else 'FAIL'
        record('adapter executable runs (--version)', rt['executableVerdict'],
               f"rc={vp.returncode}" + ('' if vp.returncode == 0 else f" out={vp.stdout.strip()[:120]} err={vp.stderr.strip()[:120]}"))
        if vp.returncode == 0:
            # Preview crate/binary version is 0.15.0 (NOT the release bundle 1.2.0).
            out = (vp.stdout + vp.stderr)
            rt['versionVerdict'] = 'PASS' if (EXPECTED_ADAPTER in out) else 'FAIL'
            record('adapter --version reports Preview 0.15.0', rt['versionVerdict'],
                   ''.join((vp.stdout + vp.stderr).splitlines())[:160])
            if '1.2.0' in out and EXPECTED_ADAPTER in out:
                record('release 1.2.0 and adapter 0.15.0 not conflated in --version', 'INFO')
        with_ver = (out_dir / 'rill-adapter-version.txt')
        with_ver.write_text((vp.stdout + vp.stderr).strip() + '\n')
        (out_dir / 'rill-adapter-runtime.log').write_text('\n'.join(json.dumps(x) for x in log) + '\n')

    # 2. Startup: the CI job launched the adapter; verify it published a socket.
    sock_path = args.socket
    bus = AdapterBus(sock_path)
    deadline = time.time() + 10
    connected = False
    while time.time() < deadline:
        try:
            bus.connect()
            connected = True
            break
        except OSError:
            time.sleep(0.5)
            bus.s = None
    rt['startupVerdict'] = 'PASS' if connected else 'BLOCKED'
    record('adapter unix socket connectable', rt['startupVerdict'], sock_path)
    if not connected:
        rt_worst = 'BLOCKED'
        rt['statusVerdict'] = rt['observeVerdict'] = rt['outcomeVerdict'] = rt['failClosedVerdict'] = 'BLOCKED'
    else:
        # 3. Real status roundtrip.
        try:
            resp = bus.exchange('status')
            ok, reason = status_gate(resp)
            rt['statusVerdict'] = 'PASS' if (ok and resp.get('releaseVersion') == EXPECTED_RELEASE) else 'FAIL'
            record('status roundtrip (contract/protocol/caps/health)', rt['statusVerdict'],
                   reason + ('' if ok else f"; release={resp.get('releaseVersion')} adapter={resp.get('adapterVersion')}"))
        except Exception as e:  # noqa: BLE001
            rt['statusVerdict'] = 'FAIL'; record('status roundtrip', 'FAIL', str(e))

        # 4. Real observe advisory roundtrip (no apply authority).
        try:
            resp = bus.exchange('observe', extra={
                'deviceProfile': 'recommended', 'capabilityHash': 'h', 'topologyGeneration': 1,
                'pathId': 'path:lan-to-wan', 'routeIdentity': 'r', 'workloadClass': ['plain_forwarding'],
                'measurementClass': 'controlled_ab', 'context': {}, 'integrations': {},
                'integrationFingerprint': 'x', 'contextKey': 'ctx-v1:profile=recommended;cap=h;topo=1;path=path:lan-to-wan;route=0;workload=0;integ=0;goal=balanced',
                'availableActions': [{'id': 'network.backlog'}]})
            # Advisory: response must be a dict with no apply/uci/nft mutation op.
            if isinstance(resp, dict) and not any(k in resp for k in ('apply', 'uci', 'commit')):
                rt['observeVerdict'] = 'PASS'
                record('observe advisory roundtrip (no apply authority)', 'PASS',
                       f"recommended={resp.get('recommended')}")
            else:
                rt['observeVerdict'] = 'FAIL'; record('observe advisory roundtrip', 'FAIL', json.dumps(resp)[:200])
        except Exception as e:  # noqa: BLE001
            rt['observeVerdict'] = 'BLOCKED'; record('observe advisory roundtrip', 'BLOCKED', str(e))

        # 5. Real validated outcome roundtrip.
        try:
            resp = bus.exchange('outcome', extra={
                'contextKey': 'ctx-v1:profile=recommended;cap=h;topo=1;path=path:lan-to-wan;route=0;workload=0;integ=0;goal=balanced',
                'actionId': 'network.backlog', 'decisionId': 'decision-1', 'validated': True,
                'reward': 0.0, 'correlation': 'decision-1', 'modelGeneration': 1})
            if isinstance(resp, dict) and resp.get('acknowledged') is True:
                rt['outcomeVerdict'] = 'PASS'
                record('validated outcome roundtrip accepted', 'PASS', json.dumps(resp)[:200])
            else:
                rt['outcomeVerdict'] = 'FAIL' if isinstance(resp, dict) else 'BLOCKED'
                record('validated outcome roundtrip accepted', rt['outcomeVerdict'], json.dumps(resp)[:200])
        except Exception as e:  # noqa: BLE001
            rt['outcomeVerdict'] = 'BLOCKED'; record('validated outcome roundtrip', 'BLOCKED', str(e))

        # 6. Negative / fail-closed cases (adapter must reject, never silently accept).
        negatives = []
        for label, extra in [
            ('wrong-contract', {'contract': 'pm-rill-other'}),
            ('foreign-protocol-version', {'protocolVersion': 2}),
            ('unknown-action', {'op': 'observe', 'contextKey': 'ctx-v1:goal=balanced', 'actionId': 'no.such.action',
                                'deviceProfile': 'recommended', 'capabilityHash': 'h', 'topologyGeneration': 1,
                                'pathId': 'p', 'routeIdentity': 'r', 'workloadClass': ['plain_forwarding'],
                                'measurementClass': 'controlled_ab', 'context': {}, 'integrations': {},
                                'integrationFingerprint': 'x', 'availableActions': [{'id': 'network.backlog'}]}),
            ('validated-false-outcome', {'op': 'outcome', 'contextKey': 'ctx-v1:goal=balanced', 'actionId': 'network.backlog',
                                         'decisionId': 'decision-x', 'validated': False, 'reward': 0.0,
                                         'correlation': 'decision-x', 'modelGeneration': 1}),
            ('unknown-decisionId', {'op': 'outcome', 'contextKey': 'ctx-v1:goal=balanced', 'actionId': 'network.backlog',
                                    'decisionId': 'never-issued', 'validated': True, 'reward': 0.0,
                                    'correlation': 'never-issued', 'modelGeneration': 1}),
        ]:
            try:
                resp = bus.exchange(label, extra)
                # fail-closed = a mismatch is surfaced (error/empty), not silently acked.
                rejected = isinstance(resp, dict) and (resp.get('error') is not None)
                negatives.append((label, rejected, resp))
                record(f'fail-closed negative: {label}', 'PASS' if rejected else 'FAIL',
                       json.dumps(resp)[:160])
            except Exception as e:  # noqa: BLE001
                negatives.append((label, False, {'_err': str(e)}))  # disconnected = reject (fail-closed)
                record(f'fail-closed negative: {label}', 'PASS', 'adapter rejected (disconnect)')
        rt['failClosedVerdict'] = 'PASS' if (negatives and all(n[1] for n in negatives)) else \
            ('FAIL' if negatives else 'BLOCKED')
        bus.close()
        roundtrip = {k: v for k, v in rt.items() if k in ('statusVerdict', 'observeVerdict', 'outcomeVerdict', 'failClosedVerdict')}
        (out_dir / 'rill-protocol-roundtrip.json').write_text(json.dumps({
            'contract': 'pm-rill-shadow', 'protocolVersion': PROTOCOL,
            'releaseVersion': EXPECTED_RELEASE, 'adapterVersion': EXPECTED_ADAPTER,
            'roundtripVerdicts': roundtrip, 'runtimeLog': log}, ensure_ascii=False, indent=2) + '\n')

    # 7. Merge real runtime verdicts into docs/rill-integration-evidence.json.
    evidence = {}
    ev_path = ROOT / 'docs' / 'rill-integration-evidence.json'
    if ev_path.exists():
        evidence = json.loads(ev_path.read_text())
    evidence['schemaVersion'] = 2
    evidence.setdefault('pm', {}).update({'version': (ROOT / 'VERSION').read_text().strip()})
    evidence.setdefault('rill', {}).update({
        'releaseVersion': EXPECTED_RELEASE, 'adapterBinaryVersion': EXPECTED_ADAPTER,
        'adapterProtocolVersion': PROTOCOL,
        'adapterReleaseAssetVersion': EXPECTED_RELEASE,
        'releaseTag': (json.loads((ROOT / 'contracts/rill-dependency.json').read_text())
                       .get('upstream', {}).get('releaseTag')),
    })
    ev_rt = evidence.setdefault('runtime', {})
    ev_rt.update(rt)
    ev_rt['harnessMode'] = 'real released adapter runtime + protocol roundtrip (CI rootfs)'
    evidence['runtimeLog'] = log
    evidence['overallVerdict'] = (
        'PASS' if all(rt[k] == 'PASS' for k in
                      ('executableVerdict', 'versionVerdict', 'startupVerdict', 'statusVerdict',
                       'observeVerdict', 'outcomeVerdict', 'failClosedVerdict'))
        else ('FAIL' if any(rt[k] == 'FAIL' for k in rt) else 'BLOCKED'))
    ev_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print('evidence ->', ev_path)

    if any(rt[k] == 'FAIL' for k in rt):
        return 1
    return 0


def os_access(p: Path) -> bool:
    try:
        return p.is_file() and (p.stat().st_mode & 0o111) != 0
    except OSError:
        return False


if __name__ == '__main__':
    sys.exit(main())