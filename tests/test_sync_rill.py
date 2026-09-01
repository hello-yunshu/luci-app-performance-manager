import importlib
import io
import os
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
sync_rill = importlib.import_module("check_rill_dependency")


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return b'{"ok": true}'


class SyncRillApiTests(unittest.TestCase):
    def test_token_is_sent_as_bearer_header(self):
        seen = []

        def fake_urlopen(request, timeout):
            seen.append((request, timeout))
            return FakeResponse()

        with patch.dict(os.environ, {"GITHUB_TOKEN": "secret-value"}), patch.object(sync_rill, "urlopen", fake_urlopen):
            self.assertEqual(sync_rill.api("rate_limit"), {"ok": True})
        self.assertEqual(seen[0][0].get_header("Authorization"), "Bearer secret-value")
        self.assertEqual(seen[0][1], 30)

    def test_missing_token_keeps_anonymous_fallback(self):
        seen = []

        def fake_urlopen(request, timeout):
            seen.append(request)
            return FakeResponse()

        with patch.dict(os.environ, {}, clear=True), patch.object(sync_rill, "urlopen", fake_urlopen):
            sync_rill.api("rate_limit")
        self.assertIsNone(seen[0].get_header("Authorization"))

    def test_403_reports_authentication_state_without_token(self):
        request = sync_rill.Request("https://api.github.com/rate_limit")

        def fake_urlopen(_request, timeout):
            raise HTTPError(request.full_url, 403, "rate limit exceeded", {}, io.BytesIO())

        with patch.dict(os.environ, {"GITHUB_TOKEN": "secret-value"}), patch.object(sync_rill, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(RuntimeError, r"GitHub API rate limit exceeded \(authenticated=true\)") as raised:
                sync_rill.api("rate_limit")
        self.assertNotIn("secret-value", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
