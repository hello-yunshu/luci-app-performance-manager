import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
UI=(ROOT/'package/luci-app-performance-manager/htdocs/luci-static/resources/view/performance-manager/benchmark.js').read_text()

class BenchmarkPersistenceTests(unittest.TestCase):
    def test_begin_refuses_unpersisted_session(self):
        body=CORE[CORE.index('function benchmark_start'):CORE.index('function benchmark_list')]
        self.assertGreaterEqual(body.count("benchmark-session-write-failed"),2)

    def test_reward_is_not_sent_if_result_cannot_be_persisted(self):
        body=CORE[CORE.index("session.state='completed'"):CORE.index("return {ok:true,stage:'result'")]
        self.assertLess(body.index('benchmark-result-write-failed-after-safe-rollback'), body.index('rill_send('))

    def test_forwarding_path_is_user_selectable(self):
        self.assertIn('pathSelect',UI)
        body=CORE[CORE.index('function benchmark_start'):CORE.index('function benchmark_list')]
        self.assertIn("path_id=msg?.pathId ?? expected_path",body)
        self.assertNotIn("path_id='path:lan-to-wan'",body)

if __name__=='__main__': unittest.main()
