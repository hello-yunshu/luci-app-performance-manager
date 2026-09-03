import json
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/docker-validate/run-local-macos.sh"
SCHEMA = ROOT / "contracts/evidence/portable-macos-docker.schema.json"


class LocalValidationTests(unittest.TestCase):
    def test_mac_validation_script_exists_and_checks_docker(self):
        text = SCRIPT.read_text()
        self.assertTrue(SCRIPT.is_file())
        self.assertIn("docker version", text)
        self.assertIn("docker info", text)
        self.assertIn("docker-unavailable", text)

    def test_mac_validation_uses_amd64_and_verifies_rootfs_checksum(self):
        text = SCRIPT.read_text()
        self.assertIn("DOCKER_PLATFORM=linux/amd64", text)
        self.assertIn("sha256sums", text)
        self.assertIn("sha256sum -c", text)
        self.assertIn("openwrt-25.12.5-x86-64-rootfs.tar.gz", text)
        self.assertIn(r"r'Ran (\d+) tests?'", text)

    def test_mac_validation_reuses_existing_gates_and_exact_artifact_identity(self):
        text = SCRIPT.read_text()
        for token in (
            "build-harness.py",
            "scripts/package_composition_gate.py",
            "scripts/portable_docker_gate.py",
            "scripts/verify_action_run_identity.py",
            "from artifact_identity import resolve_artifact",
            "repositoryCommitSha",
            "pmCommitSha",
        ):
            self.assertIn(token, text)

    def test_portable_evidence_cannot_authorize_stable_or_hardware(self):
        schema = json.loads(SCHEMA.read_text())
        self.assertEqual(schema["properties"]["profile"]["const"], "portable-macos-docker")
        self.assertEqual(schema["properties"]["hardwareCoverage"]["const"], "NOT_EVALUATED")
        self.assertIs(schema["properties"]["stableReleaseAuthorized"]["const"], False)
        sample = {
            "schemaVersion": 1,
            "profile": "portable-macos-docker",
            "pmCommitSha": "a" * 40,
            "host": {"os": "macOS", "architecture": "arm64"},
            "docker": {"platform": "linux/amd64", "version": "29"},
            "openwrt": {"version": "25.12.5", "target": "x86/64", "rootfsSha256": None},
            "sourceTests": "PASS", "coreRuntime": "BLOCKED", "runtimeV3": "BLOCKED",
            "packageComposition": "BLOCKED", "serviceSmoke": "BLOCKED", "ubusSmoke": "BLOCKED",
            "rillRemovalSmoke": "BLOCKED", "portableVerdict": "BLOCKED",
            "hardwareCoverage": "NOT_EVALUATED", "stableReleaseAuthorized": False,
            "reason": "docker-unavailable", "artifact": {"identityVerdict": "NOT_EVALUATED"},
        }
        jsonschema.Draft202012Validator(schema).validate(sample)

    def test_hardware_aggregator_does_not_accept_mac_profile(self):
        text = (ROOT / "scripts/aggregate_stable_evidence.py").read_text()
        self.assertIn('choices=("hardware", "portable-docker")', text)
        self.assertNotIn("portable-macos-docker", text)
