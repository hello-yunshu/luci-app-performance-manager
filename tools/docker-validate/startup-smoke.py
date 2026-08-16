#!/usr/bin/env python3
"""Raw shipped Core daemon startup smoke (CORE BLOCKER C evidence).

Starts the ACTUAL shipped `package/performance-manager/files/usr/sbin/
performance-manager.uc` (verbatim, zero forward references, NO convert_hoist
transform) as a real daemon inside the official OpenWrt rootfs:

  1. install the raw Core + contracts.uc into the rootfs verbatim
  2. start ubusd inside the rootfs (chroot)
  3. start the daemon inside the rootfs
  4. poll `ubus list` until the `performance-manager` object is published
  5. `ubus call` status / topology / capabilities and assert well-formed replies
  6. emit docs/core-startup-smoke.json + core-startup-smoke.log

Usage: python3 tools/docker-validate/startup-smoke.py <rootfs-dir>
The runner is expected to have passwordless sudo (chroot) and the rootfs must
contain a base OpenWrt userspace (ubusd, ubus, ucode + modules already
installed by the caller).
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / 'package/performance-manager/files/usr/sbin/performance-manager.uc'
CONTRACTS = ROOT / 'package/performance-manager/files/usr/share/performance-manager/contracts.uc'
DOCS = ROOT / 'docs'
LOG_PATH = ROOT / 'core-startup-smoke.log'
EVIDENCE_PATH = DOCS / 'core-startup-smoke.json'

POLL_TIMEOUT_S = 30
METHODS = ['status', 'topology', 'capabilities']


def sh(*argv):
    return subprocess.run(argv, capture_output=True, text=True)


def sudo_chroot(rootfs, *argv):
    return subprocess.Popen(
        ['sudo', 'chroot', str(rootfs), *argv],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        start_new_session=True,
    )


def main() -> int:
    if len(sys.argv) != 2:
        print('usage: startup-smoke.py <rootfs-dir>', file=sys.stderr)
        return 2
    rootfs = Path(sys.argv[1]).resolve()
    if not CORE.exists() or not CONTRACTS.exists():
        print(f'FATAL: shipped Core ({CORE}) or contracts ({CONTRACTS}) missing', file=sys.stderr)
        return 2

    log_lines = []
    def log(msg):
        line = f'[{time.strftime("%H:%M:%S")}] {msg}'
        log_lines.append(line)
        print(line)

    evidence = {
        'schemaVersion': 1,
        'scope': 'raw-shipped-core-daemon-startup-smoke',
        'openwrt': os.environ.get('OPENWRT_VERSION', '25.12.5'),
        'target': os.environ.get('OPENWRT_TARGET', 'x86/64'),
        'coreSource': str(CORE.relative_to(ROOT)),
        'coreSha256': hashlib.sha256(CORE.read_bytes()).hexdigest(),
        'transform': 'none',  # CORE BLOCKER C: no convert_hoist
        'ubusdStarted': False,
        'daemonStarted': False,
        'published': False,
        'ubusList': {},
        'methods': {},
        'ok': False,
    }

    procs = []
    try:
        # 1. Install the RAW shipped Core verbatim + contracts.
        log('installing raw shipped Core + contracts.uc into rootfs')
        sh('sudo', 'install', '-D', '-m', '0755', str(CORE),
           str(rootfs / 'usr/sbin/performance-manager.uc'))
        sh('sudo', 'install', '-D', '-m', '0644', str(CONTRACTS),
           str(rootfs / 'usr/share/performance-manager/contracts.uc'))
        # ubusd binds /var/run/ubus/ubus.sock and does NOT create the parent
        # directory itself (OpenWrt's /etc/init.d/ubus does mkdir -p for it), so
        # create it here for the direct-chroot ubusd start.
        sh('sudo', 'mkdir', '-p', str(rootfs / 'var/run/ubus'))
        sh('sudo', 'mkdir', '-p', str(rootfs / 'var/run'))
        sh('sudo', 'mkdir', '-p', str(rootfs / 'tmp/performance-manager'))
        sh('sudo', 'mkdir', '-p', str(rootfs / 'etc/performance-manager'))

        # 2. Start ubusd inside the rootfs.
        log('starting ubusd')
        ubusd = sudo_chroot(rootfs, '/sbin/ubusd')
        procs.append(ubusd)
        time.sleep(1.0)
        alive = ubusd.poll() is None
        evidence['ubusdStarted'] = alive
        if not alive:
            log('FATAL: ubusd exited immediately')
            return 1
        log('ubusd running (pid %d)' % ubusd.pid)

        # 3. Start the raw daemon.
        log('starting performance-manager.uc daemon (raw shipped source)')
        daemon = sudo_chroot(rootfs, '/usr/sbin/performance-manager.uc')
        procs.append(daemon)
        time.sleep(2.0)

        # 4. Poll ubus list until the object publishes.
        deadline = time.time() + POLL_TIMEOUT_S
        published = False
        listed = {}
        while time.time() < deadline:
            if daemon.poll() is not None:
                log('FATAL: daemon exited early rc=%s' % daemon.poll())
                break
            r = sh('sudo', 'chroot', str(rootfs), 'ubus', 'list')
            if r.returncode == 0:
                listed = {ln.strip() for ln in r.stdout.splitlines() if ln.strip()}
                if 'performance-manager' in listed:
                    published = True
                    break
            time.sleep(0.5)
        evidence['published'] = published
        evidence['ubusList'] = sorted(listed)
        if not published:
            log('FATAL: performance-manager object never appeared in ubus list within %ss' % POLL_TIMEOUT_S)
            return 1
        log('published: performance-manager (ubus list: %s)' % ', '.join(sorted(listed)))

        # 5. Call the core read-only methods.
        for m in METHODS:
            r = sh('sudo', 'chroot', str(rootfs), 'ubus', 'call', 'performance-manager', m)
            payload = r.stdout.strip()
            ok = r.returncode == 0 and payload.startswith('{')
            parsed = None
            if ok:
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    ok = False
            evidence['methods'][m] = {'ok': ok, 'rc': r.returncode, 'bytes': len(payload)}
            log('%s call %s -> rc=%s ok=%s bytes=%s' % ('PASS' if ok else 'FAIL', m, r.returncode, ok, len(payload)))
            if not ok:
                log('  stderr: %s' % r.stderr.strip())
                return 1
            if parsed is not None:
                log('  sample: %s' % json.dumps(parsed, ensure_ascii=False)[:220])
            if r.stderr.strip():
                log('  stderr: %s' % r.stderr.strip())

        evidence['ok'] = True
        return 0
    finally:
        log('cleaning up daemon + ubusd')
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

        LOG_PATH.write_text('\n'.join(log_lines) + '\n')
        DOCS.mkdir(exist_ok=True)
        EVIDENCE_PATH.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
        log('evidence -> %s' % EVIDENCE_PATH.relative_to(ROOT))
        log('log      -> %s' % LOG_PATH.relative_to(ROOT))
        sys.stdout.flush()
        # Flush the final log line into the file too (finally runs after the
        # return expression above has been evaluated).
        LOG_PATH.write_text('\n'.join(log_lines) + '\n')


if __name__ == '__main__':
    sys.exit(main())
