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


class SyncContractTransactionTests(unittest.TestCase):
    def test_fields_noop_release_binding_and_failed_write(self):
        import copy
        import contextlib
        import hashlib
        import json
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);package=root/'package'
            (package/'package/rill-runtime').mkdir(parents=True);(package/'metadata').mkdir()
            contract=json.loads((Path(ROOT)/'contracts/rill-runtime.json').read_text())
            raw=b'validated schema 3 fixture'
            contract['qualification'].update(runAttempt=2,manifestSha256=hashlib.sha256(raw).hexdigest())
            contract['extension']={'keep':True};contract['policy']['future']='preserve'
            destination=root/'contract.json';destination.write_text(json.dumps(contract))
            version=contract['resolved']['version'];commit=contract['openwrtPackage']['commit'];run=contract['qualification']['runId']
            metadata={'package':{'name':'rill-runtime','version':version,'release':contract['openwrtPackage']['packageRelease'],'binary':'/usr/bin/rill-runtime'},
                'upstream':{'version':version,'commit':contract['resolved']['upstreamCommit'],'archiveSha256':contract['resolved']['sourceArchiveSha256']}}
            metadata_path=package/'metadata/rill-runtime.json';metadata_path.write_text(json.dumps(metadata))
            recipe=package/'package/rill-runtime/Makefile';recipe.write_text(f"PKG_NAME:=rill-runtime\nPKG_VERSION:={version}\nPKG_RELEASE:={metadata['package']['release']}\n")
            def api(path):
                if '/releases?' in path:return [{'tag_name':'v'+version,'draft':False,'prerelease':False}]
                return {'workflow_runs':[{'id':run,'run_attempt':2,'conclusion':'success'}]}
            def proof(*args):return {'package':metadata['package'],'upstream':metadata['upstream']},raw,[]
            with patch.object(sync_rill,'CONTRACT',destination),patch.object(sync_rill,'api',api), \
                 patch.object(sync_rill,'git_head',return_value=commit),patch.object(sync_rill,'qualified_manifest',proof), \
                 contextlib.redirect_stdout(io.StringIO()):
                before=destination.read_bytes();sync_rill.sync(package);self.assertEqual(before,destination.read_bytes())
                changed=copy.deepcopy(contract);changed['qualification']['runId']=run+1;destination.write_text(json.dumps(changed))
                sync_rill.sync(package);result=json.loads(destination.read_text())
                self.assertEqual(result['extension'],contract['extension']);self.assertEqual(result['policy']['future'],'preserve')
                self.assertEqual(result['qualification']['runId'],run)
                # The package recipe release is independently bound, not merely its version.
                recipe.write_text(f'PKG_NAME:=rill-runtime\nPKG_VERSION:={version}\nPKG_RELEASE:=99\n')
                before=destination.read_bytes()
                with self.assertRaises(ValueError):sync_rill.sync(package)
                self.assertEqual(before,destination.read_bytes())
                recipe.write_text(f"PKG_NAME:=rill-runtime\nPKG_VERSION:={version}\nPKG_RELEASE:={metadata['package']['release']}\n")
                changed=json.loads(destination.read_text());changed['qualification']['runId']=run+1;destination.write_text(json.dumps(changed));before=destination.read_bytes()
                with patch.object(sync_rill.os,'replace',side_effect=OSError('injected failure')):
                    with self.assertRaises(OSError):sync_rill.sync(package)
                self.assertEqual(before,destination.read_bytes());self.assertFalse(list(root.glob('.rill-contract-*')))


if __name__ == "__main__":
    unittest.main()
