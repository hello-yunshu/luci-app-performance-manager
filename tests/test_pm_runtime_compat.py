import json
import io
import re
import tarfile
import unittest
from pathlib import Path
import tempfile
import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "package/luci-app-performance-manager-all/files/usr/share/performance-manager/rill-runtime-compat.json"
CORE = ROOT / "package/performance-manager/files/usr/sbin/performance-manager.uc"
BUNDLE = ROOT / "package/luci-app-performance-manager-all/Makefile"
ACL = ROOT / "package/luci-app-performance-manager/root/usr/share/rpcd/acl.d/luci-app-performance-manager.json"
RILL_VIEW = ROOT / "package/luci-app-performance-manager/htdocs/luci-static/resources/view/performance-manager/rill.js"
RILL_CONTRACT = ROOT / "contracts/rill-runtime.json"
BUILD_WORKFLOW = ROOT / ".github/workflows/build-openwrt.yml"
UI_WORKFLOW = ROOT / ".github/workflows/real-luci-ui.yml"
UI_PROVISION = ROOT / "tests/real-luci-ui-provision.sh"


class RuntimeCompatibilityManifestTests(unittest.TestCase):
    def test_manifest_is_installed_and_matches_the_runtime_version_pin(self):
        manifest = json.loads(MANIFEST.read_text())
        core = CORE.read_text()
        match = re.search(r"const RILL_RESOLVED_VERSION = '([^']+)'", core)
        self.assertIsNotNone(match)
        self.assertEqual(manifest["schemaVersion"], 1)
        self.assertEqual(manifest["consumer"], "luci-app-performance-manager-all")
        self.assertEqual(manifest["runtimePackage"], "rill-runtime")
        self.assertEqual(manifest["minVersion"], match.group(1))
        self.assertEqual(manifest["maxVersionExclusive"], "1.5.7")
        self.assertIn("rill-runtime-compat.json", BUNDLE.read_text())
        self.assertNotIn("maxVersion", manifest)
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        import verify_apks
        self.assertEqual(
            verify_apks.bundle_source_payloads()["/usr/share/performance-manager/rill-runtime-compat.json"],
            MANIFEST,
        )

    def test_runtime_management_rpc_is_available_to_pm_luci_users(self):
        acl = json.loads(ACL.read_text())["luci-app-performance-manager"]
        self.assertEqual(acl["read"]["ubus"]["rill-runtime-manager"], ["status"])
        self.assertEqual(acl["write"]["ubus"]["rill-runtime-manager"], ["refresh", "install", "repair", "update"])

    def test_pm_update_button_uses_pm_specific_runtime_manager_flag(self):
        view = RILL_VIEW.read_text()
        self.assertIn("manager.pmUpdateAvailable === true", view)
        self.assertNotIn("manager.clientUpdateAvailable === true", view)
        self.assertIn("manager.repairAvailable === true", view)

    def test_legacy_preview_runtime_is_detected_and_never_replaced_implicitly(self):
        view = RILL_VIEW.read_text()
        makefile = BUNDLE.read_text()
        self.assertIn("manager.channel === 'legacy-preview'", view)
        self.assertIn("manager.package === 'rill-runtime-preview'", view)
        self.assertIn("!runtimeConflict", view)
        self.assertIn("PM will not remove or replace it automatically", view)
        self.assertIn("rill-runtime-preview", makefile)
        dependency_line = next(line for line in makefile.splitlines() if line.startswith("\tDEPENDS:="))
        self.assertNotIn("rill-runtime-preview", dependency_line)

    def test_sdk_workflow_matches_exact_six_arch_dual_format_policy(self):
        policy = json.loads((ROOT / "contracts/openwrt-native-targets.json").read_text())
        workflow = yaml.safe_load((ROOT / ".github/workflows/build-openwrt.yml").read_text())
        rows = workflow["jobs"]["openwrt-sdk-build"]["strategy"]["matrix"]["include"]
        actual = {(row["openwrt_version"], row["package_arch"], row["package_manager"]) for row in rows}
        required = {(row["openwrtVersion"], row["packageArch"], row["packageManagerFormat"])
                    for row in policy["targets"]}
        self.assertEqual(actual, required)
        self.assertEqual(len(actual), 12)
        self.assertEqual({arch for _, arch, _ in actual}, {
            "x86_64", "aarch64_generic", "aarch64_cortex-a53", "aarch64_cortex-a72",
            "aarch64_cortex-a76", "arm_cortex-a7_neon-vfpv4",
        })
        steps = workflow["jobs"]["openwrt-sdk-build"]["steps"]
        install = next(step["run"] for step in steps if step.get("name") == "Install feeds and local packages")
        self.assertLess(install.index("rill-runtime"), install.index("make defconfig"))
        self.assertLess(install.index("rill-runtime-manager"), install.index("make defconfig"))
        # package-metadata.pl indents package symbols, so the gate must tolerate
        # leading whitespace before the config record.
        self.assertIn("[[:space:]]*config PACKAGE_${package}", install)

    def test_build_and_ui_workflows_use_the_locked_rill_package_commit(self):
        contract = json.loads(RILL_CONTRACT.read_text())
        commit = contract["openwrtPackage"]["commit"]
        self.assertEqual(contract["openwrtPackage"]["package"], "rill-runtime")
        self.assertTrue(commit is None or re.fullmatch(r"[0-9a-f]{40}", commit))
        build = yaml.safe_load(BUILD_WORKFLOW.read_text())
        rill_commit = build["jobs"]["openwrt-sdk-build"]["env"]["RILL_PACKAGE_COMMIT"]
        self.assertNotIn("1f9c5e0d7c02090c3ac9caab5be99feb9daf9044", rill_commit)
        self.assertIn("contract_commit", BUILD_WORKFLOW.read_text())
        ui_workflow = UI_WORKFLOW.read_text()
        self.assertIn(".openwrtPackage.commit", ui_workflow)
        self.assertIn("rev-parse HEAD", ui_workflow)
        self.assertIn("PM_RILL_MANAGER_DIR", ui_workflow)

    def test_real_luci_provision_registers_and_checks_manager_rpc_without_runtime(self):
        provision = UI_PROVISION.read_text()
        for path in (
            "files/usr/libexec/rpcd/rill-runtime-manager",
            "files/usr/libexec/rill-runtime-manager",
            "files/usr/share/rpcd/acl.d/rill-runtime-manager.json",
        ):
            self.assertIn(path, provision)
        self.assertIn("/etc/init.d/rpcd restart", provision)
        self.assertIn("ubus call rill-runtime-manager status '{}'", provision)
        self.assertIn(".ok == true and .installed == false and .channel == \"none\"", provision)

    def test_all_package_depends_on_the_shared_runtime_manager(self):
        makefile = BUNDLE.read_text()
        self.assertIn("+rill-runtime-manager", makefile)
        self.assertIn("+rill-runtime", makefile)
        self.assertNotIn("$(RILL_RUNTIME_BINARY)", makefile)

    def test_ipk_control_and_payload_are_read_from_ar_member_archives(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_apks import ipk_pkginfo, ipk_file_content

        def tar_bytes(files):
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                for name, content in files.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
            return buffer.getvalue()

        members = [
            ("debian-binary", b"2.0\n"),
            ("control.tar.gz", tar_bytes({"./control": b"Package: demo\nVersion: 1.2.3-r1\nArchitecture: x86_64\nDepends: foo, bar\nConflicts: old-runtime\n"})),
            ("data.tar.gz", tar_bytes({"./usr/share/demo/value": b"payload"})),
        ]
        data = bytearray(b"!<arch>\n")
        for name, body in members:
            header = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{0o100644:<8}{len(body):<10}`\n".encode()
            data.extend(header)
            data.extend(body)
            if len(body) % 2:
                data.extend(b"\n")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "demo.ipk"
            path.write_bytes(data)
            meta = ipk_pkginfo(path)
            self.assertEqual(meta["pkgname"], "demo")
            self.assertEqual(meta["pkgver"], "1.2.3-r1")
            self.assertEqual(meta["arch"], "x86_64")
            self.assertEqual(set(meta["depend"]), {"foo", "bar", "!old-runtime>=0"})
            self.assertEqual(ipk_file_content(path, "/usr/share/demo/value"), b"payload")

    def test_ipk_bundle_conflicts_are_required_negative_dependencies(self):
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        from verify_apks import ALL_IN_ONE, REQUIRED_DEPENDS, dependency_check, ipk_pkginfo

        conflicts = {
            "performance-manager", "luci-app-performance-manager",
            "performance-manager-rill", "rill-runtime-preview",
            "luci-i18n-performance-manager-zh-cn",
        }

        def ipk_bytes(control_text):
            def tar_bytes(files):
                buffer = io.BytesIO()
                with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
                    for name, content in files.items():
                        info = tarfile.TarInfo(name)
                        info.size = len(content)
                        archive.addfile(info, io.BytesIO(content))
                return buffer.getvalue()

            members = [
                ("debian-binary", b"2.0\n"),
                ("control.tar.gz", tar_bytes({"./control": control_text.encode()})),
                ("data.tar.gz", tar_bytes({})),
            ]
            data = bytearray(b"!<arch>\n")
            for name, body in members:
                header = f"{name + '/':<16}{0:<12}{0:<6}{0:<6}{0o100644:<8}{len(body):<10}`\n".encode()
                data.extend(header)
                data.extend(body)
                if len(body) % 2:
                    data.extend(b"\n")
            return bytes(data)

        control = (
            "Package: luci-app-performance-manager-all\n"
            "Version: 1.0.7-r7\n"
            "Architecture: x86_64\n"
            "Depends: rill-runtime, rill-runtime-manager\n"
            "Conflicts: " + ", ".join(sorted(conflicts)) + "\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "luci-app-performance-manager-all.ipk"
            path.write_bytes(ipk_bytes(control))
            metadata = ipk_pkginfo(path)

        actual_negative = {dep for dep in metadata["depend"] if dep.startswith("!")}
        expected_negative = {f"!{name}>=0" for name in conflicts}
        self.assertEqual(actual_negative, expected_negative)
        self.assertEqual(
            dependency_check(ALL_IN_ONE, metadata["depend"])[1],
            sorted(REQUIRED_DEPENDS[ALL_IN_ONE] - set(metadata["depend"])),
        )
        for missing_conflict in expected_negative:
            deps = set(metadata["depend"]) - {missing_conflict}
            ok, missing = dependency_check(ALL_IN_ONE, deps)
            self.assertFalse(ok)
            self.assertIn(missing_conflict, missing)


if __name__ == "__main__":
    unittest.main()
