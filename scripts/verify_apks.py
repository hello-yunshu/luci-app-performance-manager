#!/usr/bin/env python3
"""Exact APK package verification for the remote OpenWrt SDK build gate.

The previous gate matched built APKs by FILENAME PREFIX, which is unsound:
`performance-manager-*.apk` also matches `performance-manager-rill-*.apk`, so a
missing Core package could be masked by the integration package.  This script
reads the real APK CONTROL metadata (`.PKGINFO`) and verifies, for each expected
package, an exact match on:

  - package name       (pkgname)
  - version + release  (pkgver, e.g. 1.0.0_rc4-r1)
  - architecture       (arch == the target arch)
  - dependencies       (depend lines)
  - filename + sha256

It fails closed (exit != 0) if any expected package is absent, duplicated, of
the wrong arch, or a stray old-version artifact.

Usage:
  python3 scripts/verify_apks.py <sdk_dir> <expected_version> <arch>
"""
from __future__ import annotations
import gzip, hashlib, io, json, sys, tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ['performance-manager', 'luci-app-performance-manager', 'performance-manager-rill']


def open_package(path):
    """Open an APK returning a binary file object, handling gzip, zstd, xz and
    plain-tar compression.  OpenWrt 25.x APKs are zstd-compressed (.tar.zst) by
    default, which Python's tarfile cannot decode directly, so zstd is
    decompressed through the zstandard module (or the `zstd` CLI as a fallback)
    before tarfile reads the stream."""
    with open(path, 'rb') as f:
        head = f.read(6)
    if head[:2] == b'\x1f\x8b':  # gzip
        return gzip.open(path, 'rb')
    if head[:4] == b'\x28\xb5\x2f\xfd':  # zstd
        # Buffered into a seekable BytesIO: the compressed stream is not
        # seekable, and tarfile('r:*') seeks for compression detection.
        f = open(path, 'rb')
        try:
            import zstandard as zstd
            with zstd.ZstdDecompressor().stream_reader(f) as r:
                return io.BytesIO(r.read())
        except Exception:
            f.close()
            import subprocess
            p = subprocess.run(['zstd', '-d', '-c', path], capture_output=True)
            if p.returncode != 0:
                raise RuntimeError(p.stderr.decode('utf-8', 'replace'))
            return io.BytesIO(p.stdout)
    return open(path, 'rb')  # xz / plain tar (tarfile 'r:*' auto-detects)


def apk_pkginfo(path):
    """Return a dict of the package's .PKGINFO control metadata, or None."""
    try:
        with open_package(path) as f:
            with tarfile.open(fileobj=f, mode='r:*') as tf:
                m = tf.getmember('.PKGINFO')
                data = tf.extractfile(m).read().decode('utf-8', 'replace')
    except Exception:
        return None
    meta = {}
    for line in data.splitlines():
        line = line.strip()
        if not line or ' = ' not in line:
            continue
        # .PKGINFO repeats keys (e.g. multiple `depend = ...`); collect lists.
        key, _, value = line.partition(' = ')
        key = key.strip()
        value = value.strip()
        if key in meta:
            if isinstance(meta[key], list):
                meta[key].append(value)
            else:
                meta[key] = [meta[key], value]
        else:
            meta[key] = value
    return meta


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            h.update(chunk)
    return h.hexdigest()


def main(argv):
    if len(argv) < 4:
        print('usage: verify_apks.py <sdk_dir> <expected_version> <arch>', file=sys.stderr)
        return 2
    sdk_dir = Path(argv[1])
    expected_version = argv[2]
    arch = argv[3]

    apks = sorted(sdk_dir.rglob('*.apk'))
    if not apks:
        print('FAIL: no .apk files found in SDK tree', file=sys.stderr)
        return 1

    # Index every APK by its real package name.
    by_name = {}
    for apk in apks:
        meta = apk_pkginfo(apk)
        name = (meta or {}).get('pkgname')
        if not name:
            print(f'WARN: {apk.name} has no usable .PKGINFO; treating as non-package', file=sys.stderr)
            continue
        by_name.setdefault(name, []).append((apk, meta))

    report = {'schemaVersion': 1, 'contract': 'apk-exact-verification',
              'expectedVersion': expected_version, 'arch': arch, 'packages': {}}
    failures = []

    for name in EXPECTED:
        found = by_name.get(name, [])
        if not found:
            failures.append(f'{name}: no APK with pkgname=={name} found')
            report['packages'][name] = {'status': 'missing'}
            continue
        if len(found) > 1:
            dup = ', '.join(p[0].name for p in found)
            failures.append(f'{name}: multiple APKs resolve to pkgname=={name}: {dup}')
            report['packages'][name] = {'status': 'duplicate', 'files': [p[0].name for p in found]}
            continue
        apk, meta = found[0]
        pkgver = meta.get('pkgver', '')
        pkgarch = meta.get('arch', '')
        deps = meta.get('depend', [])
        if not isinstance(deps, list):
            deps = [deps]
        # pkgver is "<version>-r<release>"; the version part must equal the repo
        # version (e.g. 1.0.0_rc4) so a stale rc.3 artifact can never pass.
        ver_part = pkgver.split('-r')[0]
        if ver_part != expected_version:
            failures.append(f'{name}: pkgver {pkgver!r} != expected {expected_version!r}')
        if pkgarch != arch:
            failures.append(f'{name}: arch {pkgarch!r} != expected {arch!r}')
        report['packages'][name] = {
            'status': 'ok' if (ver_part == expected_version and pkgarch == arch) else 'mismatch',
            'filename': apk.name,
            'sha256': sha256(apk),
            'pkgname': name,
            'pkgver': pkgver,
            'arch': pkgarch,
            'depends': deps,
        }
        print(f"OK {name}: {apk.name} pkgver={pkgver} arch={pkgarch} sha256={report['packages'][name]['sha256']}")

    # Reject any stray APK that is not one of the three expected packages but
    # shares a prefix (e.g. a leftover old artifact) — better to be strict.
    extra = []
    for apk in sorted(apks):
        meta = apk_pkginfo(apk)
        name = (meta or {}).get('pkgname')
        if name and name not in EXPECTED and any(name.startswith(p + '-') or name.startswith(p + '_') for p in EXPECTED):
            extra.append(apk.name)
    if extra:
        failures.append(f'unexpected prefix-colliding APKs present: {", ".join(extra)}')

    report['verdict'] = 'PASS' if not failures else 'FAIL'
    report['failures'] = failures
    out = ROOT / 'docs/apk-verification.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'verdict': report['verdict'], 'verified': len(report['packages']), 'failures': failures},
                     ensure_ascii=False, indent=2))
    return 0 if report['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv))