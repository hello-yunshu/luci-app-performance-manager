#!/usr/bin/env python3
"""Render the non-promotable MacBook/Docker portable validation report."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--host-arch", required=True)
    parser.add_argument("--docker-version", default="unavailable")
    parser.add_argument("--rootfs-sha", default="")
    parser.add_argument("--source", required=True)
    parser.add_argument("--core", required=True)
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--service", required=True)
    parser.add_argument("--ubus", required=True)
    parser.add_argument("--removal", required=True)
    parser.add_argument("--portable", required=True)
    parser.add_argument("--artifact-identity", required=True)
    parser.add_argument("--reason", default="all local gates completed")
    args = parser.parse_args()

    report = {
        "schemaVersion": 1,
        "profile": "portable-macos-docker",
        "pmCommitSha": args.commit,
        "host": {"os": "macOS", "architecture": args.host_arch},
        "docker": {"platform": "linux/amd64", "version": args.docker_version},
        "openwrt": {"version": "25.12.5", "target": "x86/64",
                    "rootfsSha256": args.rootfs_sha or None},
        "sourceTests": args.source,
        "coreRuntime": args.core,
        "runtimeV3": args.runtime,
        "packageComposition": args.package,
        "serviceSmoke": args.service,
        "ubusSmoke": args.ubus,
        "rillRemovalSmoke": args.removal,
        "portableVerdict": args.portable,
        "hardwareCoverage": "NOT_EVALUATED",
        "stableReleaseAuthorized": False,
        "reason": args.reason,
        "artifact": {"identityVerdict": args.artifact_identity},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    markdown = f"""# MacBook + Docker Local Validation

- Commit SHA: `{report['pmCommitSha']}`
- Host OS / architecture: `{report['host']['os']}` / `{report['host']['architecture']}`
- Docker version: `{report['docker']['version']}`
- Docker target architecture: `{report['docker']['platform']}`
- OpenWrt: `{report['openwrt']['version']}` / `{report['openwrt']['target']}`
- OpenWrt rootfs SHA256: `{report['openwrt']['rootfsSha256'] or 'NOT_EVALUATED'}`
- Source tests: **{report['sourceTests']}**
- Core ucode runtime: **{report['coreRuntime']}**
- Exact Rill Runtime v3: **{report['runtimeV3']}**
- Package composition: **{report['packageComposition']}**
- Service smoke: **{report['serviceSmoke']}**
- ubus smoke: **{report['ubusSmoke']}**
- Rill removal smoke: **{report['rillRemovalSmoke']}**
- Portable verdict: **{report['portableVerdict']}**
- Portable 24h soak: **NOT_EVALUATED**
- Hardware coverage: **{report['hardwareCoverage']}**
- Stable release authorization: **NO**

Reason: {report['reason']}

`Mac Docker PASS != Hardware Stable PASS`. This report is portable repository-software evidence only. Real NIC, Hyper-V/KVM, LAN-WAN, router-local, sysupgrade, reboot, and real-router resource-soak gates remain outside this profile.
"""
    (args.out.parent / "LOCAL_VALIDATION.md").write_text(markdown)
    (args.out.parent.parent / "LOCAL_VALIDATION.md").write_text(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
