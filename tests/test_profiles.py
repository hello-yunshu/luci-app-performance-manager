import json
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FIELDS=['requiredPackages','recommendedPackages','conditionalPackages','expectedCommands','expectedCapabilities','targets']
class ProfileTests(unittest.TestCase):
    def setUp(self): self.ps={p.stem:json.loads(p.read_text()) for p in (ROOT/'profiles').glob('*.json')}
    def resolve(self,name,stack=()):
        self.assertNotIn(name,stack); p=self.ps[name]; out={k:[] for k in FIELDS}
        for parent in p['extends']:
            x=self.resolve(parent,stack+(name,))
            for k in FIELDS:
                for v in x[k]:
                    if v not in out[k]: out[k].append(v)
        for k in FIELDS:
            for v in p[k]:
                if v not in out[k]: out[k].append(v)
        return out
    def test_recommended_inherits_full_minimal_contract(self):
        p=self.resolve('recommended')
        self.assertIn('performance-manager',p['requiredPackages']); self.assertIn('luci-app-performance-manager',p['requiredPackages'])
        for cmd in ['ethtool','ip','tc','ss','nstat','conntrack','iperf3']: self.assertIn(cmd,p['expectedCommands'])
        self.assertIn('x86_64',p['targets'])
    def test_x86_conditional_contract_survives_inheritance(self):
        p=self.resolve('performance-x86')
        self.assertIn({'name':'procd-ujail','whenCapability':'kernel.namespaces'},p['conditionalPackages'])
        self.assertIn('performance-manager-rill',p['recommendedPackages'])
    def test_runtime_profile_checker_evaluates_all_contract_classes(self):
        s=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
        body=s[s.index('function profile_status()'):s.index('function clock_hhmm()',s.index('function profile_status()'))]
        for token in ['requiredPackages','recommendedPackages','conditionalPackages','expectedCommands','expectedCapabilities','targets','targetMatched']:
            self.assertIn(token,body)
if __name__=='__main__': unittest.main()
