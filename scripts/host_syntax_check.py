#!/usr/bin/env python3
from __future__ import annotations
import json, py_compile, shutil, subprocess, sys, tempfile
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
errors=[]; checks=[]

def run(name, cmd, *, input_text=None):
    p=subprocess.run(cmd, cwd=ROOT, input=input_text, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    checks.append({'name':name,'status':'pass' if p.returncode==0 else 'fail','output':p.stdout[-4000:]})
    if p.returncode: errors.append(f'{name}: {p.stdout.strip()}')

for rel in [
    'package/performance-manager/files/etc/init.d/performance-manager',
    'package/performance-manager/files/etc/uci-defaults/90-performance-manager',
    'package/performance-manager-rill/files/etc/init.d/performance-manager-rill',
    'scripts/openwrt-runtime-smoke.sh',
    'scripts/openwrt-target-gate.sh',
    'scripts/openwrt-resource-soak.sh',
    'scripts/openwrt-sysupgrade-gate.sh',
]: run(f'sh -n {rel}', ['sh','-n',rel])

try:
    py_compile.compile(str(ROOT/'companion/pm_companion_agent.py'), doraise=True)
    checks.append({'name':'companion py_compile','status':'pass'})
except Exception as e:
    errors.append(f'companion py_compile: {e}'); checks.append({'name':'companion py_compile','status':'fail','output':str(e)})

for p in sorted(ROOT.rglob('*.json')):
    if any(x in p.parts for x in ('.git','dist','__pycache__')): continue
    try: json.loads(p.read_text())
    except Exception as e: errors.append(f'json {p.relative_to(ROOT)}: {e}')
checks.append({'name':'JSON parse','status':'fail' if any(e.startswith('json ') for e in errors) else 'pass'})

try:
    yaml.safe_load((ROOT/'.github/workflows/ci.yml').read_text())
    checks.append({'name':'CI YAML parse','status':'pass'})
except Exception as e:
    errors.append(f'CI YAML: {e}'); checks.append({'name':'CI YAML parse','status':'fail','output':str(e)})

node=shutil.which('node')
if node:
    for p in sorted((ROOT/'package/luci-app-performance-manager/htdocs/luci-static/resources').rglob('*.js')):
        wrapped='(function(){\n'+p.read_text()+'\n})();\n'
        run(f'node --check {p.relative_to(ROOT)}',[node,'--check','-'],input_text=wrapped)
else:
    errors.append('node is required for LuCI syntax validation')

po=ROOT/'package/luci-app-performance-manager/po/zh_Hans/performance-manager.po'
msgids=[]
for line in po.read_text().splitlines():
    if line.startswith('msgid "'): msgids.append(line)
if len(msgids)!=len(set(msgids)):
    errors.append('duplicate msgid entries in zh_Hans PO')
checks.append({'name':'zh_Hans PO duplicate check','status':'fail' if len(msgids)!=len(set(msgids)) else 'pass'})

report={'checks':checks,'errorCount':len(errors),'errors':errors}
(ROOT/'docs/HOST_SYNTAX_REPORT.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if errors:
    print('HOST SYNTAX CHECK FAILED')
    for e in errors: print(' -',e)
    sys.exit(1)
print(f'HOST SYNTAX CHECK PASSED: {len(checks)} checks')
