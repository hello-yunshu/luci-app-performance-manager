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
    'scripts/openwrt-runtime-smoke.sh',
    'scripts/openwrt-target-gate.sh',
    'scripts/openwrt-resource-soak.sh',
    'scripts/openwrt-sysupgrade-gate.sh',
]: run(f'sh -n {rel}', ['sh','-n',rel])

with tempfile.TemporaryDirectory() as pycache:
    for script in [ROOT/'companion/pm_companion_agent.py', *sorted((ROOT/'scripts').glob('*.py'))]:
        try:
            cache_name = script.relative_to(ROOT).as_posix().replace('/', '_') + 'c'
            py_compile.compile(str(script), cfile=str(Path(pycache)/cache_name), doraise=True)
            checks.append({'name':f'py_compile {script.relative_to(ROOT)}','status':'pass'})
        except Exception as e:
            errors.append(f'py_compile {script.relative_to(ROOT)}: {e}')
            checks.append({'name':f'py_compile {script.relative_to(ROOT)}','status':'fail','output':str(e)})

# Scan only the repository's own JSON files.  In CI the workspace also contains
# the downloaded OpenWrt SDK tree (a subdirectory whose feeds include non-JSON
# templates like bfdd.template.json); those must not fail this check, so walk
# git-tracked files (the SDK tree is untracked), falling back to the on-disk
# walk when git is unavailable.
try:
    _out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, text=True)
    _tracked = [ROOT / p for p in _out.stdout.split('\0') if p]
except Exception:
    _tracked = [p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts]
for p in sorted(x for x in _tracked if x.suffix == '.json'):
    if any(x in p.parts for x in ('.git', 'dist', '__pycache__')): continue
    try: json.loads(p.read_text())
    except Exception as e: errors.append(f'json {p.relative_to(ROOT)}: {e}')
checks.append({'name': 'JSON parse', 'status': 'fail' if any(e.startswith('json ') for e in errors) else 'pass'})

for workflow in sorted((ROOT/'.github/workflows').glob('*.yml')):
    try:
        yaml.safe_load(workflow.read_text())
        checks.append({'name':f'YAML parse {workflow.name}','status':'pass'})
    except Exception as e:
        errors.append(f'YAML {workflow.name}: {e}')
        checks.append({'name':f'YAML parse {workflow.name}','status':'fail','output':str(e)})

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
