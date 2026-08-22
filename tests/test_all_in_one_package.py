import importlib.util
import hashlib
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "package/luci-app-performance-manager-all/Makefile"


class AllInOnePackageTests(unittest.TestCase):
    def test_version_is_synchronized_across_all_package_forms(self):
        expected = (ROOT / "VERSION").read_text().strip().replace("-rc.", "_rc")
        for makefile in sorted((ROOT / "package").glob("*/Makefile")):
            match = re.search(r"^PKG_VERSION:=(\S+)$", makefile.read_text(), re.MULTILINE)
            self.assertIsNotNone(match, makefile)
            self.assertEqual(match.group(1), expected, makefile)

    def test_bundle_is_physical_not_a_meta_package(self):
        makefile = BUNDLE.read_text()
        self.assertIn("po2lmo", makefile)
        self.assertIn("/usr/sbin/performance-manager.uc", makefile)
        self.assertIn("luci-app-performance-manager/htdocs", makefile)
        self.assertIn("luci-app-performance-manager/root/usr/share/rpcd", makefile)
        self.assertIn("performance-manager-rill/files", makefile)
        self.assertNotIn("+performance-manager ", makefile)
        self.assertNotIn("+luci-app-performance-manager", makefile)
        self.assertNotIn("PROVIDES:=", makefile)

    def test_bundle_conflicts_with_every_split_owner(self):
        makefile = BUNDLE.read_text()
        conflicts = re.search(r"^\s*CONFLICTS:=(.+)$", makefile, re.MULTILINE).group(1).split()
        self.assertEqual(set(conflicts), {
            "performance-manager",
            "luci-app-performance-manager",
            "luci-i18n-performance-manager-zh-cn",
            "performance-manager-rill",
        })

    def test_exact_verifier_maps_all_owned_source_payloads(self):
        spec = importlib.util.spec_from_file_location("verify_apks", ROOT / "scripts/verify_apks.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        payloads = module.bundle_source_payloads()
        expected_sources = []
        for source_root in (
            ROOT / "package/performance-manager/files",
            ROOT / "package/luci-app-performance-manager/htdocs",
            ROOT / "package/luci-app-performance-manager/root",
            ROOT / "package/performance-manager-rill/files",
        ):
            expected_sources.extend(p for p in source_root.rglob("*") if p.is_file())
        self.assertEqual(set(payloads.values()), set(expected_sources))
        self.assertIn("/usr/sbin/performance-manager.uc", payloads)
        self.assertIn("/www/luci-static/resources/view/performance-manager/overview.js", payloads)
        self.assertIn("/usr/share/rpcd/acl.d/luci-app-performance-manager.json", payloads)
        self.assertIn("/etc/init.d/performance-manager-rill", payloads)

    def test_remote_sdk_build_and_verifier_require_bundle(self):
        workflow = (ROOT / ".github/workflows/build-openwrt.yml").read_text()
        verifier = (ROOT / "scripts/verify_apks.py").read_text()
        evidence = (ROOT / "scripts/build_evidence.py").read_text()
        for text in (workflow, verifier, evidence):
            self.assertIn("luci-app-performance-manager-all", text)

    def test_stable_public_release_publishes_only_all_in_one_apk(self):
        workflow = (ROOT / ".github/workflows/stable-release.yml").read_text()
        self.assertIn("assemble_public_release.py", workflow)
        self.assertIn("scripts/assemble_public_release.py", workflow)
        self.assertNotIn("wc -l", workflow)
        self.assertIn("scripts/build_release_manifest.py", workflow)

    def test_prerelease_auto_publish_is_main_same_repo_release_commit_only(self):
        workflow = (ROOT / ".github/workflows/prerelease.yml").read_text()
        for token in (
            "workflow_run:",
            'workflows: ["Build OpenWrt (remote SDK)"]',
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.head_branch == 'main'",
            "github.event.workflow_run.head_repository.full_name == github.repository",
            "startsWith(github.event.workflow_run.head_commit.message, 'release:')",
            "git config user.name 'github-actions[bot]'",
            "git config user.email '41898282+github-actions[bot]@users.noreply.github.com'",
            "EXPECTED_SHA:",
            "BUILD_RUN_ID:",
        ):
            self.assertIn(token, workflow)

    def test_core_profile_checks_accept_only_the_exact_bundle_equivalence(self):
        core = (ROOT / "package/performance-manager/files/usr/sbin/performance-manager.uc").read_text()
        self.assertIn("function profile_package_installed(name)", core)
        self.assertIn("[ 'performance-manager', 'luci-app-performance-manager', 'performance-manager-rill' ]", core)
        self.assertIn("package_installed('luci-app-performance-manager-all')", core)
        self.assertIn("if (!profile_package_installed(x))", core)

    def test_release_stager_selects_only_exact_verified_bundle(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            sdk = temp / "sdk/bin/packages/x86_64/base"
            sdk.mkdir(parents=True)
            apk = sdk / "luci-app-performance-manager-all-1.0.0_rc10-r1.apk"
            apk.write_bytes(b"exact-all-in-one-apk")
            digest = hashlib.sha256(apk.read_bytes()).hexdigest()
            report = {
                "verdict": "PASS", "pmCommitSha": "a" * 40,
                "expectedVersion": "1.0.0_rc10", "arch": "x86_64",
                "packages": {"luci-app-performance-manager-all": {
                    "status": "ok", "filename": apk.name, "sha256": digest,
                    "pkgver": "1.0.0_rc10-r1", "arch": "noarch",
                    "core": {"status": "match"},
                    "installedPayload": {
                        "/usr/sbin/performance-manager.uc": {"status": "match"},
                        "/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo": {
                            "status": "compiled", "apkSha256": "b" * 64,
                        },
                    },
                }},
            }
            verification = temp / "apk-verification.json"
            verification.write_text(json.dumps(report))
            out = temp / "out"
            completed = subprocess.run([
                sys.executable, str(ROOT / "scripts/stage_all_in_one_release.py"),
                "--sdk-dir", str(temp / "sdk"), "--verification", str(verification),
                "--out", str(out),
            ], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((out / apk.name).read_bytes(), apk.read_bytes())
            manifest = json.loads((out / "all-in-one-release-manifest.json").read_text())
            self.assertEqual(manifest["apk"]["sha256"], digest)
            self.assertEqual(manifest["payloadVerification"]["fileCount"], 2)

    def test_release_assembler_accepts_same_apk_copy_in_full_and_dedicated_artifacts(self):
        with tempfile.TemporaryDirectory() as temp:
            temp = Path(temp)
            commit = "c" * 40
            version = "1.0.0-rc.10"
            apk_name = "luci-app-performance-manager-all-1.0.0_rc10-r1.apk"
            dedicated = temp / "input/openwrt-25.12.5-x86-64-all-in-one-apk"
            full = temp / "input/openwrt-25.12.5-x86-64-packages-and-evidence/sdk/bin"
            final = temp / "input/final-release-evidence-build"
            dist = temp / "dist"
            for path in (dedicated, full, final, dist):
                path.mkdir(parents=True, exist_ok=True)
            apk_bytes = b"same-verified-apk-in-two-workflow-artifacts"
            (dedicated / apk_name).write_bytes(apk_bytes)
            (full / apk_name).write_bytes(apk_bytes)
            digest = hashlib.sha256(apk_bytes).hexdigest()
            (dedicated / "all-in-one-release-manifest.json").write_text(json.dumps({
                "pmCommitSha": commit, "package": "luci-app-performance-manager-all",
                "apk": {"filename": apk_name, "sha256": digest},
            }))
            (dedicated / "all-in-one-checksums.txt").write_text(f"{digest}  {apk_name}\n")
            (full / "apk-verification.json").write_text(json.dumps({
                "verdict": "PASS", "pmCommitSha": commit,
                "packages": {"luci-app-performance-manager-all": {"status": "ok", "sha256": digest}},
            }))
            (full / "build-metadata.json").write_text(json.dumps({
                "verdict": "PASS", "repositoryCommitSha": commit,
                "packages": {"luci-app-performance-manager-all": {"apkSha256": digest}},
            }))
            (full / "FINAL_AUDIT.json").write_text("{}")
            (full / "FINAL_AUDIT.md").write_text("PASS\n")
            (final / "final-release-evidence.json").write_text(json.dumps({
                "overallVerdict": "PASS", "expectedCommitSha": commit,
            }))
            (dist / f"openwrt-performance-manager-{version}.zip").write_bytes(b"source")
            (dist / f"openwrt-performance-manager-{version}.manifest.json").write_text("{}")
            out = temp / "out"
            completed = subprocess.run([
                sys.executable, str(ROOT / "scripts/assemble_prerelease.py"),
                "--input", str(temp / "input"), "--out", str(out),
                "--expected-sha", commit, "--source-dist", str(dist), "--version", version,
            ], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((out / apk_name).read_bytes(), apk_bytes)
            self.assertTrue((out / "release-checksums.txt").is_file())
            stable_out = temp / "stable-out"
            completed = subprocess.run([
                sys.executable, str(ROOT / "scripts/assemble_public_release.py"),
                "--input", str(temp / "input"), "--out", str(stable_out),
                "--expected-commit", commit,
            ], capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual((stable_out / apk_name).read_bytes(), apk_bytes)


if __name__ == "__main__":
    unittest.main()
