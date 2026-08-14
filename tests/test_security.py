import re, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class SecurityTests(unittest.TestCase):
    def test_core_uses_execvp_arrays(self):
        s=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
        self.assertNotIn("run([ 'sh', '-c'",s)
        self.assertRegex(s,r"fs\.popen\(argv, 'r'\)")
    def test_rill_has_no_command_execution(self):
        s=(ROOT/'package/performance-manager-rill/src/src/main.rs').read_text()
        self.assertNotIn('std::process::Command',s); self.assertNotIn('Command::new',s)
        self.assertIn('SO_PEERCRED',s); self.assertIn('cred.uid != 0',s)
    def test_rill_shadow_only_ops(self):
        s=(ROOT/'package/performance-manager-rill/src/src/main.rs').read_text()
        for op in ['"status"','"observe"','"outcome"']: self.assertIn(op,s)
        for op in ['"apply"','"rollback"','"uci"']: self.assertNotIn(op,s)
