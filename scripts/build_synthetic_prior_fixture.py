#!/usr/bin/env python3
"""Build a private, lower-version full APK fixture with the official SDK.

The current, already-built full APK is extracted with the official SDK's
native ``apk`` tool, its owned payload is changed in a temporary tree, and a
new real ADB APK is generated with ``apk mkpkg``. This keeps the fixture on
the package-manager path without making a cold runner rebuild unrelated feed
dependencies. The fixture is deliberately not a release artifact and is
labelled as synthetic so it cannot be confused with a historical public
package.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path


PACKAGE = "luci-app-performance-manager-all"
PAYLOAD_PATHS = (
    "/usr/sbin/performance-manager.uc",
    "/www/luci-static/resources/view/performance-manager/overview.js",
    "/usr/bin/rill-runtime",
)
DEPENDENCIES = (
    "coreutils-timeout", "libc", "luci-base", "luci-i18n-base-zh-cn",
    "rpcd", "ubus", "uci", "ucode", "ucode-mod-fs", "ucode-mod-log",
    "ucode-mod-rtnl", "ucode-mod-socket", "ucode-mod-ubus", "ucode-mod-uci",
    "ucode-mod-uloop",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def write_scripts(directory: Path) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    scripts = {
        "post-install": "#!/bin/sh\n[ \"${IPKG_NO_SCRIPT}\" = \"1\" ] && exit 0\n[ -s ${IPKG_INSTROOT}/lib/functions.sh ] || exit 0\n. ${IPKG_INSTROOT}/lib/functions.sh\nexport root=\"${IPKG_INSTROOT}\"\nexport pkgname=\"luci-app-performance-manager-all\"\nadd_group_and_user\ndefault_postinst\n[ -n \"${IPKG_INSTROOT}\" ] || {\n    rm -f /tmp/luci-indexcache.*\n    rm -rf /tmp/luci-modulecache/\n    /etc/init.d/rpcd reload 2>/dev/null\n    exit 0\n}\n",
        "pre-deinstall": "#!/bin/sh\n[ -s ${IPKG_INSTROOT}/lib/functions.sh ] || exit 0\n. ${IPKG_INSTROOT}/lib/functions.sh\nexport root=\"${IPKG_INSTROOT}\"\nexport pkgname=\"luci-app-performance-manager-all\"\ndefault_prerm\n[ -n \"${IPKG_INSTROOT}\" ] && exit 0\n[ \"${PKG_UPGRADE:-0}\" = \"1\" ] && exit 0\n[ -x /usr/sbin/performance-manager.uc ] || exit 0\nout=$(ubus call performance-manager cleanup '{\"reason\":\"package-remove\"}' 2>/dev/null) || true\nprintf '%s' \"$out\" | grep -q '\"ok\":true' && exit 0\necho \"performance-manager: uninstall cleanup failed or daemon unreachable; start the service and retry removal\" >&2\nexit 1\n",
        "post-upgrade": "#!/bin/sh\nexport PKG_UPGRADE=1\n[ \"${IPKG_NO_SCRIPT}\" = \"1\" ] && exit 0\n[ -s ${IPKG_INSTROOT}/lib/functions.sh ] || exit 0\n. ${IPKG_INSTROOT}/lib/functions.sh\nexport root=\"${IPKG_INSTROOT}\"\nexport pkgname=\"luci-app-performance-manager-all\"\nadd_group_and_user\ndefault_postinst\n[ -n \"${IPKG_INSTROOT}\" ] || {\n    rm -f /tmp/luci-indexcache.*\n    rm -rf /tmp/luci-modulecache/\n    /etc/init.d/rpcd reload 2>/dev/null\n    exit 0\n}\n",
    }
    paths = {}
    for name, content in scripts.items():
        path = directory / name
        path.write_text(content)
        path.chmod(0o755)
        paths[name] = path
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sdk-dir", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--release", default="1")
    parser.add_argument("--package-arch", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args(argv)
    sdk = args.sdk_dir.resolve()
    out = args.out.resolve()
    apk_tool = sdk / "staging_dir/host/bin/apk"
    if not apk_tool.is_file():
        raise SystemExit(f"official SDK apk tool missing: {apk_tool}")
    current_matches = sorted(
        path for path in sdk.glob(f"bin/**/{PACKAGE}-*.apk") if path.is_file()
    )
    if len(current_matches) != 1:
        raise SystemExit(f"expected one already-built current APK, found {current_matches}")
    current_apk = current_matches[0]

    marker = f"pm-synthetic-prior-fixture:{args.version}-{args.release}:{args.commit}"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pm-synthetic-prior-") as temporary:
        temporary_root = Path(temporary)
        prior_root = temporary_root / "root"
        prior_root.mkdir()
        scripts = write_scripts(temporary_root / "scripts")
        run([
            str(apk_tool), "--allow-untrusted", "extract",
            "--destination", str(prior_root), str(current_apk),
        ], sdk)
        for relative in PAYLOAD_PATHS:
            path = prior_root / relative.lstrip("/")
            if not path.is_file():
                raise SystemExit(f"current APK is missing owned payload: {relative}")
        core = prior_root / "usr/sbin/performance-manager.uc"
        core.write_bytes(core.read_bytes() + f"\n// {marker}\n".encode())
        overview = prior_root / "www/luci-static/resources/view/performance-manager/overview.js"
        overview.write_bytes(overview.read_bytes() + f"\n// {marker}\n".encode())
        # Appending a byte keeps a valid ELF executable while making the prior
        # Runtime identity observably different from the current build.
        runtime = prior_root / "usr/bin/rill-runtime"
        runtime.write_bytes(runtime.read_bytes() + b"\n")

        target = out / f"{PACKAGE}-{args.version}-r{args.release}.apk"
        info = (
            "name:" + PACKAGE,
            f"version:{args.version}-r{args.release}",
            f"arch:{args.package_arch}",
            "license:GPL-3.0-only",
            "maintainer:OpenWrt Performance Manager contributors",
            "origin:feeds/base/openwrt-performance-manager/luci-app-performance-manager-all",
            "description:Private synthetic prior fixture for package-manager upgrade testing",
            "depends:" + " ".join(DEPENDENCIES),
            f"provides:luci-app-performance-manager-all-any performance-manager-core={args.version}-r{args.release}",
        )
        command = [str(apk_tool), "mkpkg"]
        for value in info:
            command.extend(["--info", value])
        for name, path in scripts.items():
            command.extend(["--script", f"{name}:{path}"])
        command.extend(["--files", str(prior_root), "--output", str(target)])
        run(command, sdk)
        payload = {
            payload_path: sha256(prior_root / payload_path.lstrip("/"))
            for payload_path in PAYLOAD_PATHS
        }
        metadata = {
            "schemaVersion": 1,
            "gate": "full-upgrade-prior-fixture",
            "package": PACKAGE,
            "version": args.version,
            "pkgver": f"{args.version}-r{args.release}",
            "sha256": sha256(target),
            "syntheticPriorFixture": True,
            "historicalReleaseUpgrade": False,
            "marker": marker,
            "payload": payload,
            "publicRelease": False,
            "stableReleaseAsset": False,
            "sourceCommitSha": args.commit,
            "note": "Private test fixture only; not a historical released-version artifact.",
        }
        (out / "full-upgrade-prior.json").write_text(json.dumps(metadata, indent=2) + "\n")
        print(json.dumps(metadata, indent=2))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
