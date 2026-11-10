#!/usr/bin/env python3
"""Create the hosted/Docker release gate used when hardware testbeds do not exist.

This is intentionally a different release profile from the historical hardware
matrix.  It proves the exact same-commit source, Rill, SDK and APK chain plus a
real Core ucode harness executed inside Docker.  It does not claim Hyper-V,
router hardware, sysupgrade firmware reboot, or a 24-hour soak.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


PACKAGE = "luci-app-performance-manager-all"
SHA = re.compile(r"^[0-9a-f]{64}$")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def one(root: Path, name: str) -> Path:
    matches = sorted(path for path in root.rglob(name) if path.is_file())
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one {name} under {root}, found {matches}")
    return matches[0]


def identical_artifact(root: Path, name: str) -> Path:
    matches = sorted(path for path in root.rglob(name) if path.is_file())
    if not matches:
        raise RuntimeError(f"missing {name} under {root}")
    digests = {sha256(path) for path in matches}
    if len(digests) != 1:
        raise RuntimeError(f"conflicting copies of {name} under {root}: {matches}")
    return matches[0]


def read_json(root: Path, name: str) -> dict:
    return json.loads(one(root, name).read_text())


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--build-root", required=True)
    parser.add_argument("--ci-root", required=True)
    parser.add_argument("--docker-log", required=True)
    parser.add_argument("--test-report", required=True)
    parser.add_argument("--package-report")
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    build_root = Path(args.build_root)
    ci_root = Path(args.ci_root)
    build = read_json(build_root, "build-metadata.json")
    apk = read_json(build_root, "apk-verification.json")
    test_report = json.loads(Path(args.test_report).read_text())
    docker_log = Path(args.docker_log).read_text()
    package_report = json.loads(Path(args.package_report).read_text()) if args.package_report else None
    built = (build.get("packages") or {}).get(PACKAGE) or {}
    verified = (apk.get("packages") or {}).get(PACKAGE) or {}
    apk_filename = built.get("apkFilename")
    if not isinstance(apk_filename, str) or not apk_filename:
        raise RuntimeError("build metadata lacks the exact all-in-one APK filename")
    apk_path = identical_artifact(build_root, apk_filename)
    actual_sha = sha256(apk_path)
    full_meta = build.get("fullPackage") or {}
    full_runtime = (verified.get("runtimeBinary") or {})

    final_evidence = read_json(ci_root, "final-release-evidence.json")
    final_commit = final_evidence.get("expectedCommitSha") or final_evidence.get("pmCommitSha") or final_evidence.get("commit")
    final_verdict = final_evidence.get("overallVerdict")
    checks = {
        "sourceAndTests": test_report.get("verdict") == "PASS",
        "officialSdk": build.get("repositoryCommitSha") == args.expected_commit and build.get("verdict") == "PASS",
        "exactApkVerification": (
            apk.get("pmCommitSha") == args.expected_commit
            and apk.get("verdict") == "PASS"
            and verified.get("sha256") == built.get("apkSha256") == actual_sha
            and verified.get("arch") == build.get("architecture")
            and full_runtime.get("status") == "present"
            and full_runtime.get("matchesSplitRuntime") is True
            and full_meta.get("runtimeBundled") is True
        ),
        "rillCiChain": final_commit == args.expected_commit and final_verdict == "PASS",
        "dockerCoreRuntime": "PORTABLE_DOCKER_PASS" in docker_log,
    }
    if package_report is not None:
        full_upgrade = package_report.get("fullUpgrade") or {}
        pristine = package_report.get("pristineRootfs") or {}
        checks.update({
            "packageComposition": package_report.get("verdict") == "PASS",
            "pristineRootfs": pristine.get("pristineBeforeInstall") is True,
            "fullUpgrade": full_upgrade.get("verdict") == "PASS",
            "httpsTransport": package_report.get("repositoryTransport") == "https" and
                              full_upgrade.get("transportVerdict") == "PASS",
        })
    errors = []
    if build.get("repositoryCommitSha") != args.expected_commit:
        errors.append("build metadata commit mismatch")
    if apk.get("pmCommitSha") != args.expected_commit:
        errors.append("APK verification commit mismatch")
    if not SHA.fullmatch(actual_sha):
        errors.append("APK SHA-256 is invalid")
    if built.get("apkSha256") != verified.get("sha256") or built.get("apkSha256") != actual_sha:
        errors.append("APK SHA identities disagree")
    if not all(checks.values()):
        errors.extend(f"{name} did not pass" for name, passed in checks.items() if not passed)

    result = {
        "schemaVersion": 1,
        "profile": "portable-docker",
        "gate": "portable-docker",
        "pmCommitSha": args.expected_commit,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "verdict": "PASS" if not errors else "FAIL",
        "passed": not errors,
        "checks": checks,
        "apk": {"filename": apk_path.name, "sha256": actual_sha, "version": verified.get("expectedVersion")},
        "bundledRuntime": {"package": "rill-runtime",
                            "version": build.get("rillConsumedVersion"),
                            "sourceCommit": (build.get("externalRuntime") or {}).get("commit"),
                            "sha256": full_runtime.get("sha256")},
        "hardwareCoverage": "NOT_EVALUATED",
        "stableReleaseAuthorized": False,
        "packageComposition": package_report.get("verdict") if package_report else "NOT_EVALUATED",
        "fullUpgrade": (package_report.get("fullUpgrade") or {}).get("verdict") if package_report else "NOT_EVALUATED",
        "pristineRootfs": (package_report.get("pristineRootfs") or {}).get("pristineBeforeInstall") if package_report else False,
        "repositoryTransport": package_report.get("repositoryTransport") if package_report else "NOT_EVALUATED",
        "transportVerdict": (package_report.get("fullUpgrade") or {}).get("transportVerdict") if package_report else "NOT_EVALUATED",
        "unsupportedHardwareGates": [
            "Hyper-V/vmbus/hv_netvsc", "KVM hotplug", "LAN-WAN A/B hardware",
            "router-local A/B hardware", "firmware sysupgrade reboot", "24-hour soak",
        ],
        "disclosure": "Docker/hosted evidence is sufficient for the portable release profile only; it is not hardware certification.",
        "errors": errors,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"profile": result["profile"], "verdict": result["verdict"], "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
