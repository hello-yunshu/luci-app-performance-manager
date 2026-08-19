#!/usr/bin/env python3
"""Real PM Core <-> real released rill-pm-adapter roundtrip (CI, OpenWrt rootfs).

This is the rc.7 PM-Core roundtrip gate.  It does NOT mirror the Core and does
NOT use the mock adapter.  Inside the official OpenWrt rootfs it:

  1. installs the RAW shipped performance-manager.uc + contracts.uc (verbatim),
  2. installs the EXACT verified rill-pm-adapter v1.2.0 artifact at
     /usr/bin/rill-pm-adapter (the shared empty-binary default-resolution path),
  3. starts ubusd, then the real adapter, then the real Core daemon,
  4. calls `ubus call performance-manager rill_status` and asserts the Core
     negotiated the real adapter: state available and releaseVersion 1.2.0 /
     adapterVersion 0.15.0 / protocolVersion 1,
  5. emits docs/pm-core-rill-roundtrip.json + docs/rill-core-integration.json
     (per-job evidence, rc.7) and pm-core-rill-roundtrip.log.

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


def sh(*argv):
    return subprocess.run(argv, capture_output=True, text=True)


def chroot(rootfs, *argv):
    return subprocess.Popen(['sudo', 'chroot', str(rootfs), *argv],
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, start_new_session=True)


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
                    'installTarget': '/usr/bin/rill-pm-adapter'},
        'ubusdStarted': False, 'adapterStarted': False, 'daemonStarted': False,
        'published': False, 'rillStatus': None,
        'verdict': 'BLOCKED', 'ok': False,
    }
    procs = []
    try:
        log('installing raw Core + contracts + verified adapter into rootfs')
        sh('sudo', 'install', '-D', '-m', '0755', str(CORE), str(rootfs / 'usr/sbin/performance-manager.uc'))
        sh('sudo', 'install', '-D', '-m', '0644', str(CONTRACTS), str(rootfs / 'usr/share/performance-manager/contracts.uc'))
        sh('sudo', 'install', '-D', '-m', '0755', str(adapter), str(rootfs / 'usr/bin/rill-pm-adapter'))
        # The adapter binds /run/pm-rill.sock, so the chroot needs /run (in the
        # official rootfs /run is not guaranteed to pre-exist in the tar).
        for d in ('run', 'var/run/ubus', 'var/run', 'tmp/performance-manager', 'etc/performance-manager', 'etc/performance-manager/rill'):
            sh('sudo', 'mkdir', '-p', str(rootfs / d))

        log('starting ubusd')
        ubusd = chroot(rootfs, '/sbin/ubusd')
        procs.append(ubusd)
        time.sleep(1.0)
        ev['ubusdStarted'] = ubusd.poll() is None
        if not ev['ubusdStarted']:
            log('FATAL: ubusd exited'); return 1

        log('starting real rill-pm-adapter')
        a = chroot(rootfs, '/usr/bin/rill-pm-adapter',
                   '--socket', '/run/pm-rill.sock',
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
            log('FATAL: rill-pm-adapter exited early rc=%s output=%r' % (rc, (out or '')[-800:]))
            return 1

        # Adapter publishes the socket (shared empty-binary default path is the
        # installed /usr/bin/rill-pm-adapter; socket is the Core's default).
        sock = rootfs / 'run/pm-rill.sock'
        sock_deadline = time.time() + 15
        while time.time() < sock_deadline:
            if sock.exists() and a.poll() is None:
                break
            time.sleep(0.5)
        if not sock.exists():
            log('FATAL: adapter socket never appeared'); ev['verdict'] = 'FAIL'; return 1
        log('adapter at /usr/bin/rill-pm-adapter published %s' % sock)

        log('starting raw shipped Performance Manager Core daemon')
        daemon = chroot(rootfs, '/usr/sbin/performance-manager.uc')
        procs.append(daemon)
        time.sleep(2.0)

        deadline = time.time() + POLL_TIMEOUT_S
        published = False
        while time.time() < deadline:
            if daemon.poll() is not None:
                log('FATAL: Core exited early rc=%s' % daemon.poll()); break
            r = sh('sudo', 'chroot', str(rootfs), 'ubus', 'list')
            if r.returncode == 0 and 'performance-manager' in r.stdout:
                published = True
                break
            time.sleep(0.5)
        ev['published'] = published
        if not published:
            log('FATAL: performance-manager never published'); ev['verdict'] = 'FAIL'; return 1
        log('performance-manager published')

        r = sh('sudo', 'chroot', str(rootfs), 'ubus', 'call', 'performance-manager', 'rill_status')
        payload = r.stdout.strip()
        ok = r.returncode == 0 and payload.startswith('{')
        parsed = json.loads(payload) if ok else None
        ev['rillStatus'] = parsed if parsed else payload
        state = (parsed or {}).get('state') if isinstance(parsed, dict) else None
        release = (parsed or {}).get('releaseVersion') if isinstance(parsed, dict) else None
        adapter_ver = (parsed or {}).get('adapterVersion') if isinstance(parsed, dict) else None
        proto = (parsed or {}).get('protocolVersion') if isinstance(parsed, dict) else None
        binary_effective = (((parsed or {}).get('binary') or {}).get('effective')) if isinstance(parsed, dict) else None
        pass_ = (ok and state in ('available', 'learning') and release == '1.2.0'
                 and adapter_ver == '0.15.0' and proto == 1
                 and binary_effective == '/usr/bin/rill-pm-adapter')
        ev['verdict'] = 'PASS' if pass_ else 'FAIL'
        ev['checks'] = {
            'runrc': r.returncode, 'state': state, 'releaseVersion': release,
            'adapterVersion': adapter_ver, 'protocolVersion': proto,
            'binaryEffective': binary_effective,
        }
        log('rill_status -> rc=%s state=%s release=%s adapter=%s proto=%s binary=%s => %s' % (
            r.returncode, state, release, adapter_ver, proto, binary_effective, ev['verdict']))
        if not pass_:
            log('  sample=%s' % payload[:600])
            return 1
        ev['ok'] = True
        return 0
    finally:
        for p in reversed(procs):
            if p.poll() is None:
                try:
                    os.killpg(os.getpgid(p.pid), 15)
                except Exception:
                    p.terminate()
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
            'runtime': ev.get('runtime'),
        }
        JOB_EVIDENCE_PATH.write_text(json.dumps(job_evidence, ensure_ascii=False, indent=2) + '\n')
        EVIDENCE_PATH.write_text(json.dumps(ev, ensure_ascii=False, indent=2) + '\n')
        LOG_PATH.write_text('\n'.join(lines) + '\n')
        sys.stdout.flush()


if __name__ == '__main__':
    sys.exit(main())