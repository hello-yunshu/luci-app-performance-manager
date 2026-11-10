import copy
import hashlib
import json
import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from download_conflict_preview import fixture_contract


class ConflictPreview(unittest.TestCase):
    def fixture(self):
        data={'schemaVersion':3,'releaseEligible':True,'packageCommit':'a'*40,'runId':123,'runAttempt':2,
              'package':{'name':'rill-runtime','version':'1.6.0','release':2},
              'previewPackage':{'name':'rill-runtime-preview','version':'1.7.0','release':3,
                                'upstream':{'commit':'b'*40},'qualificationState':'PASS'}}
        raw=json.dumps(data).encode()
        contract={'policy':{'track':'latest-qualified-stable'},'extension':{'keep':True},
                  'openwrtPackage':{'commit':'a'*40,'package':'rill-runtime','packageVersion':'1.6.0','packageRelease':2},
                  'qualification':{'runId':123,'runAttempt':2,'manifestSha256':hashlib.sha256(raw).hexdigest()}}
        return contract,data,raw

    def test_supported_contract_stays_stable_and_untouched(self):
        contract,data,raw=self.fixture();before=copy.deepcopy(contract)
        fixture=fixture_contract(contract,raw)
        self.assertEqual(contract,before)
        self.assertEqual(fixture['policy'],before['policy'])
        self.assertEqual(fixture['extension'],before['extension'])
        self.assertEqual(fixture['openwrtPackage']['package'],'rill-runtime-preview')
        self.assertEqual(fixture['openwrtPackage']['packageVersion'],'1.7.0')
        self.assertEqual(fixture['preview']['commit'],'b'*40)
        self.assertIn('not supported PM Runtime',fixture['testOnlyPurpose'])

    def test_wrong_run_attempt_digest_or_local_only_manifest_is_rejected(self):
        contract,data,raw=self.fixture()
        with self.assertRaises(ValueError):fixture_contract(contract,raw+b' ')
        for key,value in [('runId',124),('runAttempt',3),('packageCommit','c'*40),('schemaVersion',2),('releaseEligible',False)]:
            changed={**data,key:value};candidate=json.dumps(changed).encode();pin=copy.deepcopy(contract)
            pin['qualification']['manifestSha256']=hashlib.sha256(candidate).hexdigest()
            with self.subTest(key=key),self.assertRaises(ValueError):fixture_contract(pin,candidate)
