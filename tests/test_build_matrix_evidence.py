import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "aggregate_build_matrix_evidence", ROOT / "scripts/aggregate_build_matrix_evidence.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BuildMatrixEvidenceTests(unittest.TestCase):
    def test_aggregates_distinct_native_targets_and_rejects_no_target_shortcut(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            commit = "a" * 40
            for arch, target, fmt in (("x86_64", "x86/64", "apk"), ("aarch64_generic", "armsr/armv8", "apk")):
                target_dir = root / f"openwrt-{arch}"
                target_dir.mkdir()
                runtime_sha = ("1" if arch == "x86_64" else "2") * 64
                common = {
                    "status": "ok", "apkFilename": f"rill-runtime-{arch}.apk",
                    "apkSha256": runtime_sha, "releaseFilename": f"rill-runtime-{arch}.apk",
                }
                build = {
                    "repository": "hello-yunshu/luci-app-performance-manager",
                    "repositoryCommitSha": commit, "openwrtVersion": "25.12.5",
                    "target": target, "architecture": arch, "packageManagerFormat": fmt,
                    "sdkIdentity": f"sdk-{arch}", "sdkArchiveSha256": "3" * 64,
                    "expectedApkPackages": ["rill-runtime"],
                    "packages": {
                        "rill-runtime": common,
                    }, "verdict": "PASS",
                }
                report = {
                    "schemaVersion": 1, "pmCommitSha": commit, "expectedVersion": "1.0.3",
                    "arch": arch, "packages": {
                        "rill-runtime": {
                            "status": "ok", "filename": common["apkFilename"], "sha256": runtime_sha,
                            "releaseFilename": common["releaseFilename"],
                        },
                    }, "verdict": "PASS",
                }
                (target_dir / "build-metadata.json").write_text(json.dumps(build))
                (target_dir / "apk-verification.json").write_text(json.dumps(report))
            out = root / "out"
            self.assertEqual(MODULE.main([
                "--input", str(root), "--out", str(out), "--expected-commit", "a" * 40,
                "--expected-arch", "x86_64", "--expected-arch", "aarch64_generic",
            ]), 0)
            metadata = json.loads((out / "build-metadata.json").read_text())
            self.assertEqual(metadata["matrixCoverage"]["targetCount"], 2)
            self.assertEqual(
                len(metadata["packages"]["rill-runtime"]["targets"]), 2
            )
            self.assertEqual(json.loads((out / "apk-verification.json").read_text())["verdict"], "PASS")


if __name__ == "__main__":
    unittest.main()
