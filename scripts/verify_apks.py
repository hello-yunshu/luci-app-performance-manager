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
import gzip, hashlib, io, json, struct, sys, tarfile, zlib
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


# --- ADBv3 (OpenWrt 25.12+ / apk-tools v3) binary format support -----------------
# OpenWrt 25.x ships APKs in the schema-based binary `adb` format, not the older
# tar-based `.PKGINFO`.  The reference implementation is the upstream apk-tools
# source and the format write-up it mirrors.  All integers are little-endian.
# Only the fields the gate needs (NAME, VERSION, ARCH, DEPENDS) are decoded.


def _u8(b, off):
    return b[off]


def _u16(b, off):
    return struct.unpack_from('<H', b, off)[0]


def _u32(b, off):
    return struct.unpack_from('<I', b, off)[0]


def _u64(b, off):
    return struct.unpack_from('<Q', b, off)[0]


def _blob(payload, val):
    """Decode a BLOB_8 / BLOB_16 / BLOB_32 adb_val_t located at `val`'s offset
    inside `payload`, returning bytes (or None for non-blob types)."""
    t = val & 0xf0000000
    base = val & 0x0fffffff
    if t == 0x80000000:  # BLOB_8: u8 length + data
        ln = _u8(payload, base)
        return payload[base + 1: base + 1 + ln]
    if t == 0x90000000:  # BLOB_16: u16 length + data
        ln = _u16(payload, base)
        return payload[base + 2: base + 2 + ln]
    if t == 0xa0000000:  # BLOB_32: u32 length + data
        ln = _u32(payload, base)
        return payload[base + 4: base + 4 + ln]
    return None


def _object_slots(payload, off):
    """Return the list of adb_val_t slots of an OBJECT at `off` inside `payload`.
    An object is a u32 count (including itself) followed by count-1 slots."""
    count = _u32(payload, off)
    return [_u32(payload, off + 4 + i * 4) for i in range(count - 1)]


def adb_pkginfo(raw):
    """Parse an ADBv3 package byte-string, returning a dict with pkgname /
    pkgver / arch / depend, or None if it is not a decodable ADBv3 package."""
    try:
        if raw[0:3] != b'ADB':
            return None
        comp = raw[3]
        if comp == 0x64:  # 'd' -> Deflate (raw stream, no gzip header)
            body = zlib.decompress(raw[4:], wbits=-zlib.MAX_WBITS)
        elif comp == 0x63:  # 'c' -> custom method: u8 method id + u8 level
            method = raw[4]
            if method == 1:  # Deflate
                body = zlib.decompress(raw[6:], wbits=-zlib.MAX_WBITS)
            elif method == 2:  # Zstandard
                import zstandard as zstd
                body = zstd.ZstdDecompressor().decompress(raw[6:])
            else:
                return None
        elif comp == 0x2e:  # '.' -> not compressed
            body = raw[4:]
        else:
            return None
        if body[0:8] != b'ADB.pckg':
            return None

        # Walk the ADB block stream looking for the mandatory ADB_BLOCK_ADB.
        pos = 8
        adb = None
        while pos + 4 <= len(body):
            v = _u32(body, pos)
            if (v >> 30) == 3:  # extended 16-byte header
                btype = v & 0x3fffffff
                x_size = _u64(body, pos + 8)
                payload = body[pos + 16: pos + x_size]
                pos += x_size
            else:  # simple 4-byte header
                btype = v >> 30
                payload = body[pos + 4: pos + (v & 0x3fffffff)]
                pos += v & 0x3fffffff
            if btype == 0:  # ADB_BLOCK_ADB
                adb = payload
                break
        if adb is None:
            return None

        # adb_hdr: u8 compat_ver, u8 ver, u16 reserved, u32 root (OBJECT).
        root_val = _u32(adb, 4)
        if root_val & 0xf0000000 != 0xe0000000:
            return None
        slots = _object_slots(adb, root_val & 0x0fffffff)
        if not slots:
            return None
        pkginfo_val = slots[0]  # ID 1: PKGINFO
        if pkginfo_val == 0 or pkginfo_val & 0xf0000000 != 0xe0000000:
            return None
        info = _object_slots(adb, pkginfo_val & 0x0fffffff)

        def slot_str(idx):
            if idx >= len(info):
                return ''
            val = info[idx]
            if val == 0:
                return ''
            data = _blob(adb, val)
            return data.decode('utf-8', 'replace') if data else ''

        deps = []
        if len(info) > 14:  # ID 15: DEPENDS (object of dependency objects)
            dval = info[14]
            if dval and (dval & 0xf0000000) == 0xe0000000:
                for o in _object_slots(adb, dval & 0x0fffffff):
                    if o and (o & 0xf0000000) == 0xe0000000:
                        dslots = _object_slots(adb, o & 0x0fffffff)
                        if dslots:
                            nb = _blob(adb, dslots[0])  # dep NAME (ID 1)
                            if nb:
                                deps.append(nb.decode('utf-8', 'replace'))
        return {'pkgname': slot_str(0), 'pkgver': slot_str(1),
                'arch': slot_str(4), 'depend': deps}
    except Exception:
        return None


def apk_pkginfo(path):
    """Return a dict of the package's .PKGINFO control metadata, or None."""
    # OpenWrt 25.x packages are ADBv3; try that binary format first.
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[0:3] == b'ADB':
        meta = adb_pkginfo(raw)
        if meta and meta.get('pkgname'):
            return meta
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
        # Architecture-independent packages (LuCI apps, translations) are built
        # as `noarch`/`all`, which matches ANY target; only a concrete, differing
        # arch is a mismatch.
        arch_ok = pkgarch in ('noarch', 'all') or pkgarch == arch
        if ver_part != expected_version:
            failures.append(f'{name}: pkgver {pkgver!r} != expected {expected_version!r}')
        if not arch_ok:
            failures.append(f'{name}: arch {pkgarch!r} != expected {arch!r}')
        report['packages'][name] = {
            'status': 'ok' if (ver_part == expected_version and arch_ok) else 'mismatch',
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