#!/usr/bin/env python3
"""Exact APK package verification for the remote OpenWrt SDK build gate.

The previous gate matched built APKs by FILENAME PREFIX, which is unsound:
`performance-manager-*.apk` also matches `performance-manager-rill-*.apk`, so a
missing Core package could be masked by the integration package.  This script
reads the real APK CONTROL metadata (`.PKGINFO`) and verifies, for each expected
package, an exact match on:

  - package name       (pkgname)
  - version + release  (pkgver, e.g. 1.0.0_rc10-r1)
  - architecture       (arch == the target arch)
  - dependencies       (depend lines)
  - filename + sha256

For the `performance-manager` Core package it additionally extracts the shipped
daemon `/usr/sbin/performance-manager.uc` from the APK's ADB data blocks and
asserts it is byte-for-byte identical (SHA256) to the repo source that the
runtime harness and startup smoke execute.  The all-in-one APK is checked even
more strictly: every repository-owned Core, LuCI, rpcd and Rill-glue file must
match its source, and the compiled Simplified Chinese LMO must be present.

It fails closed (exit != 0) if any expected package is absent, duplicated, of
the wrong arch, a stray old-version artifact, or if the APK's Core file does not
match the tested source.

Usage:
  python3 scripts/verify_apks.py <sdk_dir> <expected_version> <arch>
"""
from __future__ import annotations
import gzip, hashlib, io, json, os, struct, subprocess, sys, tarfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = [
    'performance-manager',
    'luci-app-performance-manager',
    'performance-manager-rill',
    'luci-app-performance-manager-all',
]
ALL_IN_ONE = 'luci-app-performance-manager-all'
REQUIRED_DEPENDS = {
    'performance-manager': {
        'ubus', 'uci', 'ucode', 'ucode-mod-fs', 'ucode-mod-ubus', 'ucode-mod-uci',
        'ucode-mod-rtnl', 'ucode-mod-uloop', 'ucode-mod-socket', 'ucode-mod-log',
    },
    'luci-app-performance-manager': {
        'luci-base', 'rpcd', 'performance-manager', 'luci-i18n-base-zh-cn',
    },
    'performance-manager-rill': {'performance-manager'},
    ALL_IN_ONE: {
        'luci-base', 'rpcd', 'luci-i18n-base-zh-cn', 'ubus', 'uci', 'ucode',
        'ucode-mod-fs', 'ucode-mod-ubus', 'ucode-mod-uci', 'ucode-mod-rtnl',
        'ucode-mod-uloop', 'ucode-mod-socket', 'ucode-mod-log',
    },
}

# The shipped Core daemon path inside the package; its bytes must equal the
# repo source the runtime harness / startup smoke run verbatim.
CORE_PATH = '/usr/sbin/performance-manager.uc'
CORE_SRC = ROOT / 'package/performance-manager/files/usr/sbin/performance-manager.uc'
CONTRACTS_PATH = '/usr/share/performance-manager/contracts.uc'
CONTRACTS_SRC = ROOT / 'package/performance-manager/files/usr/share/performance-manager/contracts.uc'
TRANSLATION_PATH = '/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo'
TRANSLATION_DEFAULT_PATH = '/etc/uci-defaults/luci-i18n-performance-manager-zh-cn'
TRANSLATION_DEFAULT = (
    "uci set luci.languages.zh_cn='简体中文 (Simplified Chinese)'; uci commit luci\n"
).encode()


def bundle_source_payloads():
    """Map every repository-owned source file to its all-in-one install path."""
    roots = (
        (ROOT / 'package/performance-manager/files', Path('/')),
        (ROOT / 'package/luci-app-performance-manager/htdocs', Path('/www')),
        (ROOT / 'package/luci-app-performance-manager/root', Path('/')),
        (ROOT / 'package/performance-manager-rill/files', Path('/')),
    )
    payloads = {}
    for source_root, install_root in roots:
        for source in sorted(source_root.rglob('*')):
            if source.is_file():
                payload = '/' + str((install_root / source.relative_to(source_root))).lstrip('/')
                if payload in payloads:
                    raise RuntimeError(f'duplicate all-in-one payload mapping: {payload}')
                payloads[payload] = source
    return payloads


def _pm_commit():
    """PM commit SHA the evidence was produced at (same-commit chain)."""
    sha = os.environ.get('GITHUB_SHA')
    if sha:
        return sha
    try:
        return subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True).stdout.strip() or 'unknown'
    except Exception:  # noqa: BLE001
        return 'unknown'


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


def _uint(payload, val):
    """Decode an INT / INT32 / INT64 adb_val_t (embedded or indirect)."""
    t = val & 0xf0000000
    base = val & 0x0fffffff
    if t == 0x10000000:  # INT: value embedded in low 28 bits
        return base
    if t == 0x20000000:  # INT32: u32 at offset
        return _u32(payload, base)
    if t == 0x30000000:  # INT64: u64 at offset
        return _u64(payload, base)
    return 0


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


def _adb_body(raw):
    """Decompress the ADB package body (bytes after the 4-byte ADB header).

    Returns the uncompressed `ADB.pckg` body, or None if it is not a decodable
    ADBv3 package stream."""
    if raw[0:3] != b'ADB':
        return None
    comp = raw[3]
    if comp == 0x64:  # 'd' -> Deflate (raw stream, no gzip header)
        return zlib.decompress(raw[4:], wbits=-zlib.MAX_WBITS)
    if comp == 0x63:  # 'c' -> custom method: u8 method id + u8 level
        method = raw[4]
        if method == 1:  # Deflate
            return zlib.decompress(raw[6:], wbits=-zlib.MAX_WBITS)
        if method == 2:  # Zstandard
            import zstandard as zstd
            return zstd.ZstdDecompressor().decompress(raw[6:])
        return None
    if comp == 0x2e:  # '.' -> not compressed
        return raw[4:]
    return None


def _adb_blocks(body):
    """Yield (btype, payload) for every block in an `ADB.pckg` body.

    Handles both the simple 4-byte header and the extended 16-byte header, and
    skips the 8-byte alignment padding after each block (a block's raw size is
    padded up to an 8-byte boundary)."""
    if body[0:8] != b'ADB.pckg':
        return
    pos, n = 8, len(body)
    while pos + 4 <= n:
        v = _u32(body, pos)
        if (v >> 30) == 3:  # extended 16-byte header: btype in low 30 bits
            btype = v & 0x3fffffff
            raw = _u64(body, pos + 8)
            hdr = 16
        else:  # simple 4-byte header: btype in top 2 bits
            btype = v >> 30
            raw = v & 0x3fffffff
            hdr = 4
        if raw < hdr:
            return
        yield btype, body[pos + hdr: pos + raw]
        pos += raw
        pos += (8 - (raw & 7)) & 7  # 8-byte alignment padding


def _adb_root(adb):
    """Return the slot list of the ADB_BLOCK_ADB root OBJECT, or None."""
    root_val = _u32(adb, 4)
    if root_val & 0xf0000000 != 0xe0000000:
        return None
    slots = _object_slots(adb, root_val & 0x0fffffff)
    return slots or None


def _adb_pkginfo_meta(adb):
    """Parse the PKGINFO object (ID 1) of an ADB_BLOCK_ADB payload, returning a
    dict with pkgname / pkgver / arch / depend, or None."""
    slots = _adb_root(adb)
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


def _adb_paths(adb):
    """Parse the PATHS object (ID 2) of an ADB_BLOCK_ADB payload, returning a
    dict mapping (dir_idx, file_idx) -> (abs_path, size).  The 1-based indexes
    match the dir/file indexes used by the ADB_BLOCK_DATA headers."""
    slots = _adb_root(adb)
    if not slots or len(slots) < 2:
        return {}
    paths_val = slots[1]  # ID 2: PATHS (object of dir objects)
    if paths_val == 0 or paths_val & 0xf0000000 != 0xe0000000:
        return {}
    dirs = _object_slots(adb, paths_val & 0x0fffffff)
    result = {}
    for d_idx, dval in enumerate(dirs, 1):
        if dval == 0 or dval & 0xf0000000 != 0xe0000000:
            continue
        dslots = _object_slots(adb, dval & 0x0fffffff)
        dir_name = ''
        if dslots:  # ID 1: NAME
            nb = _blob(adb, dslots[0])
            if nb:
                dir_name = nb.decode('utf-8', 'replace')
        files_val = dslots[2] if len(dslots) > 2 else 0  # ID 3: FILES
        if files_val and (files_val & 0xf0000000) == 0xe0000000:
            for f_idx, fval in enumerate(_object_slots(adb, files_val & 0x0fffffff), 1):
                if fval == 0 or fval & 0xf0000000 != 0xe0000000:
                    continue
                fslots = _object_slots(adb, fval & 0x0fffffff)
                fname = ''
                if fslots:  # ID 1: NAME
                    fb = _blob(adb, fslots[0])
                    if fb:
                        fname = fb.decode('utf-8', 'replace')
                fsize = 0
                if len(fslots) > 2:  # ID 3: SIZE
                    fsize = _uint(adb, fslots[2])
                path = (dir_name + '/' + fname) if dir_name else fname
                result[(d_idx, f_idx)] = (path, fsize)
    return result


def adb_pkginfo(raw):
    """Parse an ADBv3 package byte-string, returning a dict with pkgname /
    pkgver / arch / depend, or None if it is not a decodable ADBv3 package."""
    try:
        body = _adb_body(raw)
        if body is None:
            return None
        for btype, payload in _adb_blocks(body):
            if btype == 0:  # ADB_BLOCK_ADB
                return _adb_pkginfo_meta(payload)
        return None
    except Exception:
        return None


def adb_file_content(raw, target):
    """Extract the content of a file at `target` (an absolute in-package path,
    e.g. `/usr/sbin/performance-manager.uc`) from an ADBv3 package byte-string,
    or None if it is absent.  A file's data may span multiple ADB_BLOCK_DATA
    blocks, so matching contents are concatenated up to the recorded size."""
    body = _adb_body(raw)
    if body is None:
        return None
    want = target.lstrip('/')
    found = None  # (dir_idx, file_idx, size)
    buf = bytearray()
    for btype, payload in _adb_blocks(body):
        if btype == 0:  # ADB_BLOCK_ADB: build the file -> path/size map
            for key, (path, size) in _adb_paths(payload).items():
                if path == want:
                    found = (key[0], key[1], size)
                    break
            if found is None:
                return None
            if found[2] == 0:
                return b''
        elif btype == 2 and found is not None:  # ADB_BLOCK_DATA
            key = (_u32(payload, 0), _u32(payload, 4))
            if key == (found[0], found[1]):
                buf.extend(payload[8:])
                if len(buf) >= found[2]:
                    return bytes(buf[:found[2]])
    return None


def apk_file_content(path, target):
    """Return the raw bytes of `target` inside an APK (ADBv3 or tar-based), or
    None if the file is absent."""
    with open(path, 'rb') as f:
        raw = f.read()
    if raw[0:3] == b'ADB':
        return adb_file_content(raw, target)
    want = target.lstrip('/')
    try:
        with open_package(path) as f:
            with tarfile.open(fileobj=f, mode='r:*') as tf:
                for m in tf.getmembers():
                    if m.name.lstrip('./') == want and m.isfile():
                        return tf.extractfile(m).read()
    except Exception:
        pass
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
              'pmCommitSha': _pm_commit(),
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
        missing_deps = sorted(REQUIRED_DEPENDS[name] - set(deps))
        # pkgver is "<version>-r<release>"; the version part must equal the repo
        # version (e.g. 1.0.0_rc10) so a stale candidate can never pass.
        ver_part = pkgver.split('-r')[0]
        # Architecture-independent packages (LuCI apps, translations) are built
        # as `noarch`/`all`, which matches ANY target; only a concrete, differing
        # arch is a mismatch.
        arch_ok = pkgarch in ('noarch', 'all') or pkgarch == arch
        if ver_part != expected_version:
            failures.append(f'{name}: pkgver {pkgver!r} != expected {expected_version!r}')
        if not arch_ok:
            failures.append(f'{name}: arch {pkgarch!r} != expected {arch!r}')
        if missing_deps:
            failures.append(f'{name}: required dependencies missing: {", ".join(missing_deps)}')
        identity_ok = ver_part == expected_version and arch_ok and not missing_deps
        report['packages'][name] = {
            'status': 'ok' if identity_ok else 'mismatch',
            'filename': apk.name,
            'sha256': sha256(apk),
            'pkgname': name,
            'pkgver': pkgver,
            'arch': pkgarch,
            'depends': deps,
            'requiredDepends': sorted(REQUIRED_DEPENDS[name]),
            'missingDepends': missing_deps,
        }
        # Core, and every repository-owned file in the all-in-one APK, must be
        # byte-for-byte identical to the source exercised by local gates.
        if name in ('performance-manager', ALL_IN_ONE):
            installed_payload = {}
            source_payloads = (
                {CORE_PATH: CORE_SRC, CONTRACTS_PATH: CONTRACTS_SRC}
                if name == 'performance-manager' else bundle_source_payloads()
            )
            for payload_path, source_path in source_payloads.items():
                payload_rec = {'path': payload_path}
                apk_payload = apk_file_content(apk, payload_path)
                src_sha = sha256(source_path) if source_path.is_file() else None
                if apk_payload is None:
                    payload_rec['status'] = 'missing'
                    failures.append(f'{name}: {payload_path} not found inside APK')
                elif not src_sha:
                    payload_rec['status'] = 'no-source'
                    payload_rec['size'] = len(apk_payload)
                    payload_rec['apkSha256'] = hashlib.sha256(apk_payload).hexdigest()
                    failures.append(f'{name}: cannot compare payload (repo source {source_path.name} missing)')
                else:
                    apk_sha = hashlib.sha256(apk_payload).hexdigest()
                    payload_rec.update({'status': 'match' if apk_sha == src_sha else 'mismatch',
                                        'size': len(apk_payload), 'apkSha256': apk_sha, 'sourceSha256': src_sha})
                    if apk_sha != src_sha:
                        failures.append(f'{name}: APK {payload_path} sha256 != shipped source ({apk_sha} vs {src_sha})')
                installed_payload[payload_path] = payload_rec
                print(f"PAYLOAD {name}: {payload_path} {payload_rec.get('status')} "
                      f"apk={payload_rec.get('apkSha256', '-')} src={payload_rec.get('sourceSha256', '-')}")
            if name == ALL_IN_ONE:
                default_payload = apk_file_content(apk, TRANSLATION_DEFAULT_PATH)
                default_sha = hashlib.sha256(TRANSLATION_DEFAULT).hexdigest()
                default_rec = {'path': TRANSLATION_DEFAULT_PATH, 'sourceSha256': default_sha}
                if default_payload is None:
                    default_rec['status'] = 'missing'
                    failures.append(f'{name}: {TRANSLATION_DEFAULT_PATH} not found inside APK')
                else:
                    actual_sha = hashlib.sha256(default_payload).hexdigest()
                    default_rec.update({'status': 'match' if actual_sha == default_sha else 'mismatch',
                                        'size': len(default_payload), 'apkSha256': actual_sha})
                    if actual_sha != default_sha:
                        failures.append(f'{name}: translation UCI default does not match expected content')
                installed_payload[TRANSLATION_DEFAULT_PATH] = default_rec

                translation = apk_file_content(apk, TRANSLATION_PATH)
                translation_rec = {'path': TRANSLATION_PATH}
                if not translation:
                    translation_rec['status'] = 'missing-or-empty'
                    failures.append(f'{name}: compiled Simplified Chinese translation missing or empty')
                else:
                    translation_rec.update({'status': 'compiled', 'size': len(translation),
                                            'apkSha256': hashlib.sha256(translation).hexdigest()})
                installed_payload[TRANSLATION_PATH] = translation_rec
            report['packages'][name]['installedPayload'] = installed_payload
            report['packages'][name]['core'] = installed_payload[CORE_PATH]
        print(f"OK {name}: {apk.name} pkgver={pkgver} arch={pkgarch} sha256={report['packages'][name]['sha256']}")

    # Reject any stray APK that is not one of the expected packages but
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
