#!/usr/bin/env python3
"""Verify PM layouts share one qualified Runtime package with other consumers."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from verify_apks import apk_file_content, apk_pkginfo


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pkginfo(tool: Path, path: Path) -> dict:
    return json.loads(subprocess.check_output(
        [str(tool), '--allow-untrusted', 'adbdump', '--format', 'json', str(path)], text=True
    ))['info']


def verify(args):
    if not __debug__:
        raise RuntimeError('ownership verification requires assertions')
    tool = args.apk.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    feed = output / 'feed'
    feed.mkdir()
    inputs = {name: getattr(args, name).resolve() for name in ('full', 'runtime', 'core', 'luci', 'glue')}
    expected = {'full': 'luci-app-performance-manager-all', 'runtime': 'rill-runtime',
                'core': 'performance-manager', 'luci': 'luci-app-performance-manager',
                'glue': 'performance-manager-rill'}
    packages = {}
    products = {}
    def add_to_feed(path: Path) -> tuple[dict, Path]:
        info = pkginfo(tool, path)
        filename = f"{info['name']}-{info['version']}.apk"
        if not re.fullmatch(r'[A-Za-z0-9+_.~-]+\.apk', filename):
            raise ValueError('unsafe APK repository filename')
        target = feed / filename
        if target.exists() and digest(target) != digest(path):
            raise ValueError('different APK bytes share one repository identity: ' + filename)
        if not target.exists():
            shutil.copyfile(path, target)
        return info, target

    for role, path in inputs.items():
        info, target = add_to_feed(path)
        assert info['name'] == expected[role], (role, info)
        packages[role] = target
        products[role] = {'file': target.name, 'sha256': digest(path), 'pkgver': info['version'],
                          'arch': info['arch'], 'depends': info.get('depends', info.get('depend', []))}

    # Resolve against the real dependency APKs built or shipped in this SDK,
    # not a partial repo containing only the consumer packages. This keeps the
    # install simulation meaningful for required OpenWrt libraries as well as
    # the shared Runtime provider.
    for path in sorted(args.sdk_dir.resolve().joinpath('bin').rglob('*.apk')):
        info = apk_pkginfo(path)
        if not info:
            continue
        add_to_feed(path)

    runtime = apk_file_content(inputs['runtime'], '/usr/bin/rill-runtime')
    assert runtime and hashlib.sha256(runtime).hexdigest() == args.runtime_sha256
    assert apk_file_content(inputs['runtime'], '/usr/share/rill/runtime-channel') == b'stable\n'
    assert 'rill-runtime' in products['full']['depends']
    assert 'rill-runtime' in products['glue']['depends']
    assert apk_file_content(inputs['full'], '/usr/bin/rill-runtime') is None

    # Build a neutral third-party package whose only relationship to Rill is
    # the public package dependency. This proves APK resolves both consumers to
    # the same installed provider without either consumer owning the binary.
    with tempfile.TemporaryDirectory(prefix='rill-consumer-probe-') as temporary:
        tmp = Path(temporary)
        empty = tmp / 'empty'
        empty.mkdir()
        probe = tmp / 'generic-rill-consumer-probe.apk'
        command = [str(tool), 'mkpkg', '--compression', 'none', '--xattrs=no',
                   '--info', 'name:generic-rill-consumer-probe', '--info', 'version:1-r0',
                   '--info', 'arch:noarch', '--info', 'license:MIT',
                   '--info', 'description:Generic package dependency probe',
                   '--info', 'depends:rill-runtime', '--files', str(empty),
                   '--output', str(probe)]
        subprocess.run(command, check=True, capture_output=True)
        info = pkginfo(tool, probe)
        filename = f"{info['name']}-{info['version']}.apk"
        shutil.copyfile(probe, feed / filename)
        packages['consumer'] = feed / filename
        products['consumer'] = {'file': filename, 'sha256': digest(probe), 'pkgver': info['version'],
                                'arch': info['arch'], 'depends': info.get('depends', info.get('depend', []))}

    index = feed / 'packages.adb'
    subprocess.run([str(tool), 'mkndx', '--allow-untrusted', '--output', str(index),
                    *map(str, sorted(feed.glob('*.apk')))], check=True, capture_output=True)
    cases = []
    arch = products['runtime']['arch']
    scenarios = [('all-in-one-plus-independent-consumer', ['full', 'consumer']),
                 ('split-pm-plus-independent-consumer', ['core', 'luci', 'glue', 'consumer'])]
    for name, roles in scenarios:
        root = output / name
        (root / 'etc/apk/keys').mkdir(parents=True)
        (root / 'repositories').write_text('file://' + str(index) + '\n')
        state = root / 'etc/performance-manager/rill/ownership-state'
        state.parent.mkdir(parents=True)
        state.write_bytes(b'preserve independent user state\n')
        mode = [] if os.geteuid() == 0 else ['--usermode']
        base = [str(tool), *mode, '--root', str(root), '--arch', arch, '--allow-untrusted',
                '--no-network', '--cache=no', '--keys-dir', str(root / 'etc/apk/keys'),
                '--repositories-file', str(root / 'repositories')]
        result = subprocess.run([*base, '--no-scripts', 'add', '--initdb',
                                 *[packages[role] for role in roles]],
                                capture_output=True, text=True, timeout=120)
        (root / 'install.json').write_text(json.dumps({'exitCode': result.returncode,
            'stdout': result.stdout, 'stderr': result.stderr}, indent=2) + '\n')
        assert result.returncode == 0, result.stdout + result.stderr
        installed = sorted(subprocess.check_output([*base, 'info'], text=True).splitlines())
        assert installed.count('rill-runtime') == 1, 'shared Runtime was not installed exactly once'
        runtime_path = root / 'usr/bin/rill-runtime'
        assert hashlib.sha256(runtime_path.read_bytes()).hexdigest() == args.runtime_sha256
        assert (root / 'usr/share/rill/runtime-channel').read_bytes() == b'stable\n'
        assert state.read_bytes() == b'preserve independent user state\n'
        cases.append({'scenario': name, 'installedPackages': installed,
                      'singleRuntimeOwner': True, 'runtimeBinarySha256': args.runtime_sha256,
                      'independentConsumerInstalled': 'generic-rill-consumer-probe' in installed,
                      'statePreserved': True})

    result = {'scope': 'Full/split PM and independent consumers sharing Stable Runtime',
              'releaseEligible': False, 'deviceQualification': False,
              'runtimeBinarySha256': args.runtime_sha256, 'products': products, 'cases': cases}
    (output / 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('apk', 'full', 'runtime', 'core', 'luci', 'glue', 'output', 'sdk-dir'):
        parser.add_argument('--' + key, type=Path, required=True)
    parser.add_argument('--runtime-sha256', required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args), indent=2))


if __name__ == '__main__':
    main()
