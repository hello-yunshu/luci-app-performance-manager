#!/usr/bin/env python3
"""Real PM Core <-> PM-owned adapter lifecycle (CI, OpenWrt rootfs).

This is the stable PM-Core lifecycle gate.  It does NOT mirror the Core and does
NOT use the mock adapter.  Inside the official OpenWrt rootfs it:

  1. installs the RAW shipped performance-manager.uc + contracts.uc (verbatim),
  2. installs the EXACT verified PM-owned adapter artifact at its canonical path,
  3. starts ubusd, then the real adapter, then the real Core daemon,
  4. calls `ubus call performance-manager rill_status` and asserts the Core
     negotiated the real adapter against the contract release/adapter/protocol identity,
  5. drives production Core recommendations -> real Observe -> exact decision
     reservation -> duplicate-execution rejection -> controlled local A/B ->
     safe rollback -> persistent real Outcome,
  6. restarts both Core and adapter between lifecycle phases and proves the
     frozen session and upstream pending-decision state survive,
  7. emits docs/pm-core-rill-roundtrip.json + docs/rill-core-integration.json
     (per-job evidence) and pm-core-rill-roundtrip.log.

Usage: python3 tools_ok/rill_core_roundtrip.py <rootfs-dir> <adapter-binary>
The runner needs passwordless sudo (chroot).  Any verdict that cannot be proven
is FAIL/BLOCKED -- never a fabricated PASS.
"""
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / 'package/performance-manager/files/usr/sbin/performance-manager.uc'
CONTRACTS = ROOT / 'package/performance-manager/files/usr/share/performance-manager/contracts.uc'
DOCS = ROOT / 'docs'
LOG_PATH = ROOT / 'pm-core-rill-roundtrip.log'
EVIDENCE_PATH = DOCS / 'pm-core-rill-roundtrip.json'
# Per-job evidence (prompt section 27): this job owns ONLY this file so it can
# never race pm-rill-runtime writing a shared JSON.  The final aggregator merges
# per-job files by PM commit SHA.
JOB_EVIDENCE_PATH = DOCS / 'rill-core-integration.json'
POLL_TIMEOUT_S = 45
DEP = json.loads((ROOT / 'contracts/rill-dependency.json').read_text())
EXPECTED_RELEASE = DEP['rillMl']['version']
EXPECTED_ADAPTER = DEP['adapter']['version']
EXPECTED_PROTOCOL = DEP['protocol']['protocolVersion']


def sh(*argv):
    return subprocess.run(argv, capture_output=True, text=True)


def chroot(rootfs, *argv):
    return subprocess.Popen(['sudo', 'chroot', str(rootfs), *argv],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True)


def stop_process(proc):
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), 15)
        proc.wait(timeout=5)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:  # noqa: BLE001
            pass


def ubus_call(rootfs, method, payload=None):
    argv = ['sudo', 'chroot', str(rootfs), '/bin/ubus', 'call',
            'performance-manager', method]
    if payload is not None:
        argv.append(json.dumps(payload, separators=(',', ':')))
    result = sh(*argv)
    if result.returncode != 0:
        raise RuntimeError(f'ubus {method} rc={result.returncode}: {result.stderr.strip() or result.stdout.strip()}')
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f'ubus {method} returned non-JSON: {result.stdout[:400]!r}') from exc


def wait_for_core(rootfs, daemon):
    deadline = time.time() + POLL_TIMEOUT_S
    while time.time() < deadline:
        if daemon.poll() is not None:
            return False
        result = sh('sudo', 'chroot', str(rootfs), '/bin/ubus', 'list')
        if result.returncode == 0 and 'performance-manager' in result.stdout:
            return True
        time.sleep(0.5)
    return False


def companion_evidence(session, phase, bits_per_second):
    return {
        'contract': 'pm-companion/v2', 'role': session['companion']['requiredRole'],
        'ok': True, 'bitsPerSecond': bits_per_second,
        'sessionId': session['sessionId'], 'phase': phase,
        'actionId': session['actionId'], 'pathId': session['evaluationPath'],
        'topologyGeneration': session['topologyGeneration'],
        'routeIdentity': session['routeIdentity'],
        'capabilityHash': session['capabilityHash'],
        'methodology': {
            'host': 'router-local-ci', 'port': 5201, 'reverse': False,
            'parallel': 1, 'duration': 10, 'protocol': 'iperf3-tcp',
            'tool': 'iperf3', 'toolVersion': 'ci-fixture-1',
        },
    }


def _pm_commit():
    try:
        return subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip() or 'unknown'
    except Exception:  # noqa: BLE001
        return 'unknown'


def main() -> int:
    if len(sys.argv) != 3:
        print('usage: rill_core_roundtrip.py <rootfs-dir> <adapter-binary>', file=sys.stderr)
        return 2
    rootfs = Path(sys.argv[1]).resolve()
    adapter = Path(sys.argv[2]).resolve()
    if not CORE.exists() or not CONTRACTS.exists():
        print('FATAL: shipped Core/contracts missing', file=sys.stderr)
        return 2
    if not adapter.is_file():
        print(f'FATAL: verified adapter {adapter} missing', file=sys.stderr)
        return 2

    lines = []
    def log(msg):
        lines.append(f'[{time.strftime("%H:%M:%S")}] {msg}')
        print(lines[-1])

    ev = {
        'schemaVersion': 2, 'scope': 'real-core-to-real-adapter-roundtrip',
        'openwrt': os.environ.get('OPENWRT_VERSION', '25.12.5'),
        'pmCommitSha': os.environ.get('GITHUB_SHA', None) or _pm_commit(),
        'coreSha256': hashlib.sha256(CORE.read_bytes()).hexdigest(),
        'adapter': {'name': adapter.name,
                    'sha256': hashlib.sha256(adapter.read_bytes()).hexdigest(),
                    'installTarget': '/usr/sbin/performance-manager-rill-adapter'},
        'ubusdStarted': False, 'adapterStarted': False, 'daemonStarted': False,
        'published': False, 'rillStatus': None,
        'lifecycle': {
            'observeAccepted': False, 'exactDecisionFrozen': False,
            'coreRestartSurvived': False, 'candidateApplied': False,
            'adapterRestartSurvived': False, 'candidateRolledBack': False,
            'outcomeAccepted': False, 'modelGeneration': None,
        },
        'verdict': 'BLOCKED', 'ok': False,
    }
    procs = []
    try:
        log('installing raw Core + contracts + verified adapter into rootfs')
        sh('sudo', 'install', '-D', '-m', '0755', str(CORE), str(rootfs / 'usr/sbin/performance-manager.uc'))
        sh('sudo', 'install', '-D', '-m', '0644', str(CONTRACTS), str(rootfs / 'usr/share/performance-manager/contracts.uc'))
        sh('sudo', 'install', '-D', '-m', '0755', str(adapter), str(rootfs / 'usr/sbin/performance-manager-rill-adapter'))
        # Core's unique default is /run/performance-manager/rill.sock.  The
        # official rootfs does not guarantee these runtime directories exist.
        for d in ('run', 'run/performance-manager', 'var/run/ubus', 'var/run',
                  'tmp/performance-manager', 'etc/performance-manager',
                  'etc/performance-manager/rill', 'proc/sys/net/core'):
            sh('sudo', 'mkdir', '-p', str(rootfs / d))
        # A private regular-file sysctl fixture inside the unmounted rootfs
        # makes network.buffers a real Core provider without mutating the host
        # kernel.  Core still performs its production read/apply/readback/
        # rollback transaction against this path.
        fixture = rootfs / 'proc/sys/net/core/rmem_max'
        seeded = subprocess.run(['sudo', '/usr/bin/tee', str(fixture)], input='212992\n',
                                capture_output=True, text=True)
        if seeded.returncode != 0:
            log(f'FATAL: could not seed private sysctl fixture: {seeded.stderr.strip()}')
            return 1

        log('starting ubusd')
        ubusd = chroot(rootfs, '/sbin/ubusd')
        procs.append(ubusd)
        time.sleep(1.0)
        ev['ubusdStarted'] = ubusd.poll() is None
        if not ev['ubusdStarted']:
            log('FATAL: ubusd exited'); return 1

        log('starting real performance-manager-rill-adapter')
        a = chroot(rootfs, '/usr/sbin/performance-manager-rill-adapter',
                   '--socket', '/run/performance-manager/rill.sock',
                   '--state-dir', '/etc/performance-manager/rill',
                   '--max-message', '65536', '--timeout-ms', '1000')
        procs.append(a)
        time.sleep(1.5)
        ev['adapterStarted'] = a.poll() is None
        if not ev['adapterStarted']:
            rc = a.poll()
            out = ''
            try:
                out, _ = a.communicate(timeout=3)
            except Exception:
                pass
            log('FATAL: performance-manager-rill-adapter exited early rc=%s output=%r' % (rc, (out or '')[-800:]))
            return 1

        # Adapter publishes the socket at the Core's canonical default path.
        sock = rootfs / 'run/performance-manager/rill.sock'
        sock_deadline = time.time() + 15
        while time.time() < sock_deadline:
            if sock.exists() and a.poll() is None:
                break
            time.sleep(0.5)
        if not sock.exists():
            log('FATAL: adapter socket never appeared'); ev['verdict'] = 'FAIL'; return 1
        log('adapter at /usr/sbin/performance-manager-rill-adapter published %s' % sock)

        log('starting raw shipped Performance Manager Core daemon')
        daemon = chroot(rootfs, '/usr/sbin/performance-manager.uc')
        procs.append(daemon)
        time.sleep(2.0)
        published = wait_for_core(rootfs, daemon)
        ev['published'] = published
        ev['daemonStarted'] = daemon.poll() is None
        if not published:
            log('FATAL: performance-manager never published'); ev['verdict'] = 'FAIL'; return 1
        log('performance-manager published')

        parsed = ubus_call(rootfs, 'rill_status')
        payload = json.dumps(parsed, separators=(',', ':'))
        ok = isinstance(parsed, dict)
        ev['rillStatus'] = parsed if parsed else payload
        state = (parsed or {}).get('state') if isinstance(parsed, dict) else None
        release = (parsed or {}).get('rillVersion') if isinstance(parsed, dict) else None
        adapter_ver = (parsed or {}).get('adapterVersion') if isinstance(parsed, dict) else None
        proto = (parsed or {}).get('protocolVersion') if isinstance(parsed, dict) else None
        binary_effective = (((parsed or {}).get('binary') or {}).get('effective')) if isinstance(parsed, dict) else None
        pass_ = (ok and state in ('available', 'learning') and release == EXPECTED_RELEASE
                 and adapter_ver == EXPECTED_ADAPTER and proto == EXPECTED_PROTOCOL
                 and binary_effective == '/usr/sbin/performance-manager-rill-adapter')
        status_verdict = 'PASS' if pass_ else 'FAIL'
        # Status compatibility is one sub-gate, not the lifecycle verdict.
        # Keep the overall evidence BLOCKED until Observe -> exact execution ->
        # rollback -> Outcome has completed; never emit PASS with ok=false.
        ev['verdict'] = 'BLOCKED' if pass_ else 'FAIL'
        ev['checks'] = {
            'runrc': 0, 'state': state, 'releaseVersion': release,
            'adapterVersion': adapter_ver, 'protocolVersion': proto,
            'binaryEffective': binary_effective, 'statusVerdict': status_verdict,
        }
        log('rill_status -> rc=%s state=%s release=%s adapter=%s proto=%s binary=%s => %s' % (
            0, state, release, adapter_ver, proto, binary_effective, status_verdict))
        if not pass_:
            log('  sample=%s' % payload[:600])
            return 1
        # Production recommendations() performs the real Observe and returns
        # the exact advisory/binding selected by the released adapter.
        recommendations = ubus_call(rootfs, 'recommendations')
        advisory = (recommendations.get('learnedAdvisory') or [None])[0]
        observation = recommendations.get('rillObservation') or {}
        if not isinstance(advisory, dict) or observation.get('ok') is not True:
            log('FATAL: production Core did not accept a real Observe/advisory')
            ev['checks']['recommendations'] = recommendations
            ev['verdict'] = 'FAIL'
            return 1
        if advisory.get('actionId') != 'network.buffers' or advisory.get('authority') != 'advisory-only' \
                or advisory.get('executionAuthority') != 'benchmark':
            log(f"FATAL: expected sole usable network.buffers benchmark advisory, got {advisory}")
            ev['checks']['recommendations'] = recommendations
            ev['verdict'] = 'FAIL'
            return 1
        ev['lifecycle']['observeAccepted'] = True
        ev['lifecycle']['decisionId'] = advisory.get('decisionId')
        ev['lifecycle']['actionId'] = advisory.get('actionId')
        log(f"real Observe accepted decision={advisory['decisionId'][:12]}… action={advisory['actionId']}")

        begin = ubus_call(rootfs, 'benchmark_start', {
            'phase': 'begin', 'actionId': advisory['actionId'],
            'pathId': 'path:local-endpoint', 'measurementClass': 'controlled_ab',
            'executionSource': 'benchmark-rill', 'decisionId': advisory['decisionId'],
        })
        if begin.get('ok') is not True or begin.get('stage') != 'control':
            log(f'FATAL: exact Rill decision did not freeze into benchmark: {begin}')
            ev['checks']['benchmarkBegin'] = begin
            ev['verdict'] = 'FAIL'
            return 1
        session = begin['session']
        frozen = session.get('rillDecision') or {}
        exact = (session.get('executionSource') == 'benchmark-rill'
                 and frozen.get('decisionId') == advisory['decisionId']
                 and frozen.get('actionId') == advisory['actionId'])
        if not exact:
            log(f'FATAL: session lacks the exact frozen decision: {session}')
            ev['verdict'] = 'FAIL'
            return 1
        ev['lifecycle']['exactDecisionFrozen'] = True
        ev['lifecycle']['sessionId'] = session['sessionId']

        duplicate = ubus_call(rootfs, 'benchmark_start', {
            'phase': 'begin', 'actionId': advisory['actionId'],
            'pathId': 'path:local-endpoint', 'measurementClass': 'controlled_ab',
            'executionSource': 'benchmark-rill', 'decisionId': advisory['decisionId'],
        })
        if duplicate.get('ok') is not False or duplicate.get('error') != 'rill-decision-already-reserved':
            log(f'FATAL: exact decision obtained a second execution owner: {duplicate}')
            ev['checks']['duplicateDecision'] = duplicate
            ev['verdict'] = 'FAIL'
            return 1
        ev['lifecycle']['duplicateExecutionRejected'] = True

        # Restart Core while the frozen session is awaiting control.  The
        # binding cache is deliberately memory-only; the durable session must
        # carry the exact execution binding without a fresh Observe.
        stop_process(daemon)
        daemon = chroot(rootfs, '/usr/sbin/performance-manager.uc')
        procs.append(daemon)
        if not wait_for_core(rootfs, daemon):
            log('FATAL: Core did not republish after lifecycle restart')
            ev['verdict'] = 'FAIL'
            return 1
        resumed = ubus_call(rootfs, 'benchmark_status', {'sessionId': session['sessionId']})
        resumed_session = resumed.get('session') or {}
        if resumed_session.get('state') != 'awaiting_control' or \
                (resumed_session.get('rillDecision') or {}).get('decisionId') != advisory['decisionId']:
            log(f'FATAL: frozen session did not survive Core restart: {resumed}')
            ev['verdict'] = 'FAIL'
            return 1
        ev['lifecycle']['coreRestartSurvived'] = True

        control = ubus_call(rootfs, 'benchmark_start', {
            'phase': 'control', 'sessionId': session['sessionId'],
            'evidence': companion_evidence(resumed_session, 'control', 1_000_000),
        })
        if control.get('ok') is not True or control.get('stage') != 'candidate':
            log(f'FATAL: candidate was not applied through production Core: {control}')
            ev['checks']['benchmarkControl'] = control
            ev['verdict'] = 'FAIL'
            return 1
        ev['lifecycle']['candidateApplied'] = True

        # Restart the exact adapter after Observe and before Outcome.  Its
        # persistent decision ledger must preserve the pending decision.
        stop_process(a)
        a = chroot(rootfs, '/usr/sbin/performance-manager-rill-adapter',
                   '--socket', '/run/performance-manager/rill.sock',
                   '--state-dir', '/etc/performance-manager/rill',
                   '--max-message', '65536', '--timeout-ms', '1000')
        procs.append(a)
        deadline = time.time() + 15
        restarted_status = {}
        while time.time() < deadline:
            if sock.exists() and a.poll() is None:
                try:
                    restarted_status = ubus_call(rootfs, 'rill_status')
                    if restarted_status.get('state') in ('available', 'learning'):
                        break
                except RuntimeError:
                    pass
            time.sleep(0.5)
        if a.poll() is not None or not sock.exists() or \
                restarted_status.get('state') not in ('available', 'learning'):
            log('FATAL: adapter did not restart with persisted state')
            ev['verdict'] = 'FAIL'
            return 1
        ev['lifecycle']['adapterRestartSurvived'] = True

        candidate = ubus_call(rootfs, 'benchmark_start', {
            'phase': 'candidate', 'sessionId': session['sessionId'],
            'evidence': companion_evidence(resumed_session, 'candidate', 1_100_000),
        })
        result = ((candidate.get('session') or {}).get('result') or {})
        if candidate.get('ok') is not True or candidate.get('stage') != 'result' \
                or result.get('validated') is not True or result.get('rolledBack') is not True:
            log(f'FATAL: controlled candidate did not validate/rollback: {candidate}')
            ev['checks']['benchmarkCandidate'] = candidate
            ev['verdict'] = 'FAIL'
            return 1
        restored_value = fixture.read_text().strip()
        if restored_value != '212992':
            log(f'FATAL: provider fixture was not restored exactly: {restored_value!r}')
            ev['verdict'] = 'FAIL'
            return 1
        ev['lifecycle']['candidateRolledBack'] = True

        # The lightweight resources surface exposes production Core counters
        # without recomputing the full diagnostics bundle.  The accepted
        # outcome counter is exact evidence for this completed session.
        resources = ubus_call(rootfs, 'resources')
        counters = (((resources.get('resources') or {}).get('rillCounters')) or {})
        if counters.get('rillOutcomeAccepted', 0) < 1:
            log(f'FATAL: production Core did not record accepted Outcome: {counters}')
            ev['checks']['rillCounters'] = counters
            ev['verdict'] = 'FAIL'
            return 1
        ev['lifecycle']['outcomeAccepted'] = True
        ev['lifecycle']['rillCounters'] = counters

        state_file = rootfs / 'etc/performance-manager/rill/adapter-state.json'
        adapter_state = json.loads(state_file.read_text()) if state_file.exists() else {}
        ev['lifecycle']['modelGeneration'] = adapter_state.get('modelGeneration')
        if adapter_state.get('modelGeneration') != 1:
            log(f"FATAL: audited adapter modelGeneration expected 1, got {adapter_state.get('modelGeneration')!r}")
            ev['verdict'] = 'FAIL'
            return 1

        ev['checks']['benchmarkResult'] = {
            'sessionId': session['sessionId'], 'actionId': session['actionId'],
            'reward': result.get('reward'), 'validated': result.get('validated'),
            'rolledBack': result.get('rolledBack'), 'fixtureRestored': restored_value,
        }
        ev['verdict'] = 'PASS'
        ev['ok'] = True
        log('production Observe -> frozen controlled A/B -> rollback -> Outcome: PASS')
        return 0
    finally:
        for p in reversed(procs):
            stop_process(p)
        for p in procs:
            try:
                p.wait(timeout=5)
            except Exception:
                pass
        # Per-job evidence (prompt section 27): this job owns ONLY its own file;
        # it never merges into a shared rill-integration-evidence.json that a
        # parallel job (pm-rill-runtime) could overwrite.  The final aggregator
        # merges per-job files by PM commit SHA.
        job_evidence = {
            'schemaVersion': 2,
            'contract': 'pm<->rill-core-integration',
            'pmCommitSha': ev['pmCommitSha'],
            'scope': ev['scope'],
            'openwrt': ev['openwrt'],
            'verdict': ev['verdict'],
            'ok': ev['ok'],
            'coreSha256': ev['coreSha256'],
            'adapter': ev['adapter'],
            'checks': ev.get('checks'),
            'rillStatus': ev.get('rillStatus'),
            'lifecycle': ev.get('lifecycle'),
        }
        JOB_EVIDENCE_PATH.write_text(json.dumps(job_evidence, ensure_ascii=False, indent=2) + '\n')
        EVIDENCE_PATH.write_text(json.dumps(ev, ensure_ascii=False, indent=2) + '\n')
        LOG_PATH.write_text('\n'.join(lines) + '\n')
        sys.stdout.flush()


if __name__ == '__main__':
    sys.exit(main())
