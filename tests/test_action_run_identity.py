import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_action_run_identity import validate_run_identity  # noqa: E402


class ActionRunIdentityTests(unittest.TestCase):
    sha = "a" * 40
    workflow = "Build OpenWrt (remote SDK)"

    def valid(self):
        return {"conclusion": "success", "headSha": self.sha, "workflowName": self.workflow, "event": "push"}

    def test_exact_successful_run_is_accepted(self):
        self.assertEqual(validate_run_identity(self.valid(), self.sha, self.workflow), [])

    def test_wrong_sha_is_rejected(self):
        data = self.valid(); data["headSha"] = "b" * 40
        self.assertTrue(validate_run_identity(data, self.sha, self.workflow))

    def test_cancelled_and_failed_runs_are_rejected(self):
        for conclusion in ("cancelled", "failure", None):
            data = self.valid(); data["conclusion"] = conclusion
            self.assertTrue(validate_run_identity(data, self.sha, self.workflow))

    def test_wrong_workflow_is_rejected(self):
        data = self.valid(); data["workflowName"] = "CI"
        self.assertTrue(validate_run_identity(data, self.sha, self.workflow))

    def test_path_repository_and_run_metadata_are_bound_for_release(self):
        data = {**self.valid(), "path": ".github/workflows/build-openwrt.yml",
                "repository": {"full_name": "hello-yunshu/luci-app-performance-manager"},
                "workflowDatabaseId": 123, "runAttempt": 1, "headBranch": "main"}
        self.assertEqual(validate_run_identity(data, self.sha, self.workflow,
                                                ".github/workflows/build-openwrt.yml",
                                                "hello-yunshu/luci-app-performance-manager"), [])
        data["path"] = ".github/workflows/ci.yml"
        self.assertTrue(validate_run_identity(data, self.sha, self.workflow,
                                              ".github/workflows/build-openwrt.yml",
                                              "hello-yunshu/luci-app-performance-manager"))


if __name__ == "__main__":
    unittest.main()
