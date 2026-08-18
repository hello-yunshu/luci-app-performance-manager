import json, re, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
SCHEMA=json.loads((ROOT/'contracts/rill-ipc.schema.json').read_text())

class SecurityTests(unittest.TestCase):
    def test_core_uses_safe_shell_quoting(self):
        # ucode's fs.popen rejects an argv ARRAY on the supported OpenWrt runtime
        # (returns null, so every command would silently fail). The portable form
        # is a single shell-joined string where EACH argument is POSIX-quoted
        # (shell_quote), so argv elements survive the /bin/sh round-trip and no
        # bare user/program text is ever concatenated into the shell unquoted.
        s=CORE
        # No unsafe bare `sh -c` with an unquoted template string.
        self.assertNotIn("run([ 'sh', '-c'",s)
        # The runner must POSIX-quote each argument before joining.
        self.assertRegex(s,r"function shell_quote\(arg\)")
        self.assertRegex(s,r"replace\(s, /'/g, \"'\\\\''\"\)")
        # fs.popen is invoked with the joined, quoted string — never a raw array.
        self.assertRegex(s,r"fs\.popen\(cmd, 'r'\)")
    def test_rill_contract_is_shadow_only_no_apply(self):
        # Rill is an external runtime; the shadow-only contract is enforced on
        # the PM side: the Core only ever sends status/observe/outcome and the
        # formal IPC schema never admits an apply/rollback/uci op.
        self.assertIn("const RILL_REQUIRED_OPS = [ 'status', 'observe', 'outcome' ]",CORE)
        ops=SCHEMA['properties']['op']['enum']
        self.assertIn('status',ops); self.assertIn('observe',ops); self.assertIn('outcome',ops)
        for forbidden in ['apply','rollback','uci']:
            self.assertNotIn(forbidden,ops)
    def test_rill_capability_gate_is_fail_closed(self):
        # Missing runtime / unreachable service / contract or protocol mismatch
        # must be fail-closed (unavailable/incompatible), never silently OK.
        self.assertIn('external-runtime-not-provisioned',CORE)
        self.assertIn('contract-mismatch',CORE)
        self.assertIn('protocol-version-mismatch',CORE)
        self.assertIn('RILL_CONTRACT',CORE)
        self.assertIn('RILL_PROTOCOL_VERSION',CORE)
    def test_rill_has_no_direct_write_authority(self):
        # The Core never grants Rill write authority: no apply op, no root
        # apply path, and the integration is advisory-only.
        self.assertIn("authority: 'advisory-only'",CORE)
        self.assertIn("authority: 'safe-direct'",CORE)
        self.assertNotIn('"apply"',[SCHEMA['properties']['op']['enum']])
    def test_rill_missing_is_not_whole_rc_pass(self):
        # A missing/incompatible Rill integration must surface as a distinct
        # compatibility state, not hide behind a healthy Core.
        self.assertIn("state: RILL_STATES.incompatible",CORE)
        self.assertIn("reason: 'protocol-version-mismatch'",CORE)
if __name__=='__main__': unittest.main()