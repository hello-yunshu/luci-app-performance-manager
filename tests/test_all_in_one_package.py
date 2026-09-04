import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "package/luci-app-performance-manager-all/Makefile"


class AllInOnePackageTests(unittest.TestCase):
    def test_bundle_is_target_specific_and_contains_runtime_glue(self):
        makefile = BUNDLE.read_text()
        for token in (
            "po2lmo", "/usr/sbin/performance-manager.uc",
            "luci-app-performance-manager/htdocs",
            "luci-app-performance-manager/root/usr/share/rpcd",
            "performance-manager-rill/files/lib/upgrade/keep.d/performance-manager-rill",
            "RILL_RUNTIME_BINARY", "$(INSTALL_BIN) $(RILL_RUNTIME_BINARY) $(1)/usr/bin/rill-runtime",
        ):
            self.assertIn(token, makefile)
        self.assertNotIn("PKGARCH:=all", makefile)
        self.assertNotIn("+rill-runtime", makefile)
        self.assertIn("exact qualified", makefile)

    def test_bundle_conflicts_with_every_split_owner(self):
        makefile = BUNDLE.read_text()
        conflicts = next(line.split(":=", 1)[1].split() for line in makefile.splitlines()
                         if line.strip().startswith("CONFLICTS:=") )
        self.assertEqual(set(conflicts), {
            "performance-manager", "luci-app-performance-manager",
            "performance-manager-rill", "rill-runtime",
            "luci-i18n-performance-manager-zh-cn",
        })

    def test_split_rill_still_consumes_external_runtime(self):
        rill = (ROOT / "package/performance-manager-rill/Makefile").read_text()
        self.assertIn("DEPENDS:=+performance-manager-core +rill-runtime", rill)
        self.assertNotIn("cargo", rill.lower())

    def test_full_payload_map_includes_glue_keep_rule(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import verify_apks
        payloads = verify_apks.bundle_source_payloads()
        self.assertIn("/lib/upgrade/keep.d/performance-manager-rill", payloads)
        self.assertIn("/usr/sbin/performance-manager.uc", payloads)
        self.assertIn("/usr/share/rpcd/acl.d/luci-app-performance-manager.json", payloads)

    def test_public_release_stager_emits_exact_four_files_and_normalized_names(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from assemble_public_release import TARGETS, assemble_public_apk
        from verify_public_release_assets import verify_public_assets
        commit = "c" * 40
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "input"
            root.mkdir()
            for arch in TARGETS:
                target = root / f"openwrt-{arch}"
                target.mkdir()
                source_name = f"luci-app-performance-manager-all-1.0.4-r1_{arch}.apk"
                apk = target / source_name
                apk.write_bytes(f"full-{arch}".encode())
                digest = hashlib.sha256(apk.read_bytes()).hexdigest()
                build = {
                    "repositoryCommitSha": commit, "architecture": arch,
                    "target": TARGETS[arch][0], "verdict": "PASS",
                    "packages": {"luci-app-performance-manager-all": {
                        "status": "ok", "apkFilename": source_name, "apkSha256": digest,
                    }},
                    "fullPackage": {"runtimeBundled": True},
                }
                report = {
                    "pmCommitSha": commit, "arch": arch, "verdict": "PASS",
                    "packages": {"luci-app-performance-manager-all": {
                        "status": "ok", "filename": source_name, "sha256": digest,
                        "arch": arch, "runtimeBinary": {
                            "status": "present", "matchesSplitRuntime": True,
                        },
                    }},
                }
                (target / "build-metadata.json").write_text(json.dumps(build))
                (target / "apk-verification.json").write_text(json.dumps(report))
            out = Path(directory) / "public"
            assemble_public_apk(input_root=root, output_root=out,
                                expected_commit=commit, version="1.0.4")
            files = verify_public_assets(out, "1.0.4")
            self.assertEqual(files, [
                "SHA256SUMS.txt",
                "performance-manager-all-v1.0.4-aarch64_cortex-a53.apk",
                "performance-manager-all-v1.0.4-aarch64_generic.apk",
                "performance-manager-all-v1.0.4-x86_64.apk",
            ])

    def test_public_release_rejects_evidence_leaks(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_public_release_assets import verify_public_assets
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for arch in ("x86_64", "aarch64_generic", "aarch64_cortex-a53"):
                (root / f"performance-manager-all-v1.0.4-{arch}.apk").write_bytes(arch.encode())
            (root / "SHA256SUMS.txt").write_text("\n".join(
                f"{hashlib.sha256((root / f'performance-manager-all-v1.0.4-{arch}.apk').read_bytes()).hexdigest()}  performance-manager-all-v1.0.4-{arch}.apk"
                for arch in ("x86_64", "aarch64_generic", "aarch64_cortex-a53")
            ) + "\n")
            (root / "evidence.json").write_text("{}")
            with self.assertRaises(RuntimeError):
                verify_public_assets(root, "1.0.4")

    def test_full_package_declares_upgrade_safe_conffile_and_prerm(self):
        makefile = BUNDLE.read_text()
        self.assertIn("define Package/luci-app-performance-manager-all/conffiles", makefile)
        self.assertIn("/etc/config/performance-manager", makefile)
        self.assertIn('[ "$${PKG_UPGRADE:-0}" = "1" ] && exit 0', makefile)
        self.assertIn("upgradeSemantics", (ROOT / "scripts/package_composition_gate.py").read_text())

    def test_workflows_use_private_evidence_and_public_whitelist(self):
        build = (ROOT / ".github/workflows/build-openwrt.yml").read_text()
        stable = (ROOT / ".github/workflows/stable-release.yml").read_text()
        prerelease = (ROOT / ".github/workflows/prerelease.yml").read_text()
        for workflow in (build, stable, prerelease):
            self.assertIn("release-public", workflow)
            self.assertIn("verify_public_release_assets.py", workflow)
            self.assertNotIn("release-assets/*", workflow)
        self.assertIn("--evidence-dir release-evidence", build)
        self.assertIn('gh release create "$tag" release-public/*', stable)
        self.assertIn("Hardware Stable not yet qualified", prerelease)

    def test_full_composition_gate_has_one_file_fault_and_uninstall_paths(self):
        gate = (ROOT / "scripts/package_composition_gate.py").read_text()
        for token in (
            'ALL_IN_ONE = ("luci-app-performance-manager-all",)',
            "PM_FULL_RILL_FAULT_SMOKE=PASS", "PM_FULL_UNINSTALL_SMOKE=PASS",
            "PM_FULL_CONFLICT_SMOKE=PASS", "apk del luci-app-performance-manager-all",
        ):
            self.assertIn(token, gate)

    def test_portable_mac_installs_full_apk_once(self):
        script = (ROOT / "tools/docker-validate/run-local-macos.sh").read_text()
        self.assertIn("PM_FULL_APK", script)
        self.assertIn("one-file-installed bundled Rill Runtime v3 integration", script)
        self.assertNotIn("PM_RILL_APK", script)


if __name__ == "__main__":
    unittest.main()
