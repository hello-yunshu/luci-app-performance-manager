import importlib.util
import pathlib
import unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('pm_companion',ROOT/'companion/pm_companion_agent.py'); pm=importlib.util.module_from_spec(spec); spec.loader.exec_module(pm)
class CompanionTests(unittest.TestCase):
    def test_contract_is_v2(self): self.assertEqual(pm.CONTRACT,'pm-companion/v2')
    def test_reward_envelope(self):
        out=pm.compare_results({'bitsPerSecond':100.0},{'bitsPerSecond':110.0},'network.backlog','path:lan-to-wan',5,'route-v2:x')
        self.assertAlmostEqual(out['reward'],0.1); self.assertEqual(out['validationScope'],'endpoint-measurement-only'); self.assertTrue(out['oneVariable'])
    def test_client_parser_carries_core_context(self):
        parser=pm.build_parser(); a=parser.parse_args(['client','--host','1.2.3.4','--role','lan-client','--session-id','s','--phase','control','--action-id','network.backlog','--path-id','path:lan-to-wan','--topology-generation','5','--route-identity','r','--capability-hash','h'])
        self.assertEqual((a.session_id,a.phase,a.action_id,a.topology_generation,a.capability_hash),('s','control','network.backlog',5,'h'))
    def test_no_shell_execution(self):
        text=(ROOT/'companion/pm_companion_agent.py').read_text(); self.assertIn('shell=False',text); self.assertNotIn('shell=True',text)
if __name__=='__main__': unittest.main()
