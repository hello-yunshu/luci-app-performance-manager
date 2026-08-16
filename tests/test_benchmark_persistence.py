import unittest
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CORE=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
UI=(ROOT/'package/luci-app-performance-manager/htdocs/luci-static/resources/view/performance-manager/benchmark.js').read_text()

def function_body(src,name):
    # Single-function body extraction by brace matching (skipping strings and
    # comments).  The shipped Core is reordered callee-before-caller, so
    # neighbouring-function slicing would be unstable.
    m=re.search(r'function '+re.escape(name)+r'\s*\(',src)
    if not m: raise KeyError('function '+name+' not found')
    start=m.start(); i=src.index('{',start); depth=0
    while i<len(src):
        c=src[i]
        if c=='`':
            i+=1
            while i<len(src):
                if src[i]=='\\': i+=2; continue
                if src[i]=='`': break
                i+=1
            i+=1; continue
        if c in "'\"":
            q=c; i+=1
            while i<len(src):
                if src[i]=='\\': i+=2; continue
                if src[i]==q: break
                i+=1
            i+=1; continue
        if c=='/' and src[i:i+2]=='//':
            i=src.index('\n',i); continue
        if c=='/' and src[i:i+2]=='/*':
            j=src.find('*/',i); i=(j+2) if j>=0 else len(src); continue
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0: return src[start:i+1]
        i+=1
    return src[start:]

class BenchmarkPersistenceTests(unittest.TestCase):
    def test_begin_refuses_unpersisted_session(self):
        body=function_body(CORE,'benchmark_start')
        self.assertGreaterEqual(body.count("benchmark-session-write-failed"),2)

    def test_reward_is_not_sent_if_result_cannot_be_persisted(self):
        body=function_body(CORE,'benchmark_start')
        self.assertLess(body.index('benchmark-result-write-failed-after-safe-rollback'), body.index('rill_send('))

    def test_forwarding_path_is_user_selectable(self):
        self.assertIn('pathSelect',UI)
        body=function_body(CORE,'benchmark_start')
        self.assertIn("path_id=msg?.pathId ?? expected_path",body)
        self.assertNotIn("path_id='path:lan-to-wan'",body)

if __name__=='__main__': unittest.main()
