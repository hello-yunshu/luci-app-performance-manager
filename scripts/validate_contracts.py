#!/usr/bin/env python3
from __future__ import annotations
import ast, json, re, sys
from pathlib import Path
import jsonschema
ROOT=Path(__file__).resolve().parents[1]
errors=[]
def fail(msg): errors.append(msg)
def load(p):
    try:return json.loads(p.read_text())
    except Exception as e: fail(f'invalid JSON {p.relative_to(ROOT)}: {e}'); return None

# Parse every implementation JSON and validate all frozen profile contracts.
for p in sorted((ROOT/'profiles').glob('*.json'))+sorted((ROOT/'contracts').glob('*.json'))+sorted((ROOT/'schemas').glob('*.json')): load(p)
profile_schema=load(ROOT/'contracts/profile.schema.json')
profiles={p.stem:load(p) for p in (ROOT/'profiles').glob('*.json')}
for name,obj in profiles.items():
    try: jsonschema.Draft202012Validator(profile_schema).validate(obj)
    except Exception as e: fail(f'profile {name}: {getattr(e,"message",e)}')

def resolve(name,stack=()):
    if name in stack: raise ValueError('profile cycle: '+' -> '.join(stack+(name,)))
    if name not in profiles: raise ValueError(f'missing profile {name}')
    fields=['requiredPackages','recommendedPackages','conditionalPackages','expectedCommands','expectedCapabilities','targets']; out={k:[] for k in fields}; chain=[]
    for parent in profiles[name].get('extends',[]):
        m,c=resolve(parent,stack+(name,))
        for k in fields:
            for x in m[k]:
                if x not in out[k]: out[k].append(x)
        for x in c:
            if x not in chain: chain.append(x)
    for k in fields:
        for x in profiles[name].get(k,[]):
            if x not in out[k]: out[k].append(x)
    chain.append(name); return out,chain
for name in profiles:
    try: resolve(name)
    except ValueError as e: fail(str(e))
for p in (ROOT/'profiles').glob('*.json'):
    frozen=ROOT/'docs/planning-v0.3.2/profiles'/p.name
    if frozen.exists() and load(p)!=load(frozen): fail(f'profile drift from frozen plan: {p.name}')

pairs={
'action.example.json':'action.schema.json','fastpath-action.example.json':'action.schema.json','capability.example.json':'capability.schema.json',
'target-ref.example.json':'target-ref.schema.json','topology-path.example.json':'topology-path.schema.json','transaction.example.json':'transaction.schema.json',
'rill-ipc.example.json':'rill-ipc.schema.json','profile.schema.example.json':'profile.schema.json','persistence.example.json':'persistence.schema.json',
'lock.example.json':'lock.schema.json','health.example.json':'health.schema.json','benchmark-session.example.json':'benchmark-session.schema.json',
'companion-measurement.example.json':'companion-measurement.schema.json'}
for ex,sch in pairs.items():
    obj=load(ROOT/'schemas'/ex); schema=load(ROOT/'contracts'/sch)
    if obj is not None and schema is not None:
        try: jsonschema.Draft202012Validator(schema).validate(obj)
        except Exception as e: fail(f'{ex} violates {sch}: {getattr(e,"message",e)}')
# Every formal schema must ship in Core payload and stay identical.
dest=ROOT/'package/performance-manager/files/usr/share/performance-manager/schemas'
for sch in (ROOT/'contracts').glob('*.schema.json'):
    dst=dest/sch.name
    if not dst.exists(): fail(f'runtime schema missing: {sch.name}')
    elif load(sch)!=load(dst): fail(f'runtime schema drift: {sch.name}')

core=(ROOT/'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text(); contracts=(ROOT/'package/performance-manager/files/usr/share/performance-manager/contracts.uc').read_text(); make=(ROOT/'package/performance-manager/Makefile').read_text()
for m in ['ucode-mod-fs','ucode-mod-ubus','ucode-mod-uci','ucode-mod-rtnl','ucode-mod-uloop','ucode-mod-socket','ucode-mod-log']:
    if m not in make: fail(f'core dependency missing {m}')
core_pkg=re.search(r'define Package/performance-manager\n(.*?)\nendef',make,re.S)
for forbidden in ['+rpcd','+luci-base','+performance-manager-rill']:
    if core_pkg and forbidden in core_pkg.group(1): fail(f'Core hard dependency forbidden: {forbidden}')
required_ubus=['status','capabilities','topology','targets','paths','analyze','recommendations','transactions','locks','history','apply','confirm','rollback','benchmark_start','benchmark_status','benchmark_stop','rill_status','rill_refresh','diagnostics']
assert "cleanup: { args: { reason: 'string' }, call:" in core \
       and "cleanup_owned(req.args?.reason ?? 'package-remove')" in core, \
       'root-only ownership cleanup method/payload policy missing'
publish=core[core.find('conn.publish(UBUS_NAME'):]
for method in required_ubus:
    if not re.search(rf'\b{re.escape(method)}\s*:',publish): fail(f'ubus method missing: {method}')
if "run([ 'sh', '-c'" in core or 'run([ "sh", "-c"' in core: fail('shell -c execution forbidden')
for token in ['pending_marker_path','arm_commit_confirm','deadlineMonotonicMs = monotonic_ms()','core-crash-recovery','boot-recovery-runtime-reset-no-stale-replay','live-state-drift-refuses-stale-rollback']:
    if token not in core: fail(f'transaction safety mechanism missing: {token}')
if core.rfind('uloop.init();')>core.rfind('recover_pending();'): fail('recover_pending runs before uloop initialization')
for token in ['rtnl.listener','[ 16, 17, 24, 25 ]',"'-j', '-4', 'route'","'-j', '-4', 'rule', 'show'",'wanCandidates','routeProvider']:
    if token not in core: fail(f'topology/route mechanism missing: {token}')
for token in ['dns_health()','proxy_health()','vpn_health()','thermal_health()','recent_oom_state()','persistentStorageWritable','high-cpu-steal']:
    if token not in core: fail(f'health mechanism missing: {token}')
for token in ['function profile_package_installed(name)',
              "[ 'performance-manager', 'luci-app-performance-manager', 'performance-manager-rill' ]",
              "package_installed('luci-app-performance-manager-all')",
              'if (!profile_package_installed(x))']:
    if token not in core: fail(f'all-in-one profile equivalence missing: {token}')
for token in ["'/etc/init.d/packet_steering'","'/usr/libexec/network/packet-steering.uc'","'/usr/libexec/platform/packet-steering.sh'","policy: 'observe-respect'"]:
    if token not in core: fail(f'Native Packet Steering observe/respect missing: {token}')

def function_body(src,name):
    # Extract a single function body by brace matching (skipping strings and
    # comments).  The shipped Core is reordered callee-before-caller, so
    # neighbouring-function slicing would be unstable.
    m=re.search(r'function '+re.escape(name)+r'\s*\(',src)
    if not m: return ''
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

# Benchmark must use explicit evidence + the common transaction/rollback engine.
bench=function_body(core,'benchmark_start')
for token in ['companion_evidence_valid(','benchmark_apply_candidate(','rollback_transaction(session.transactionId',"validated:true","validated:false"]:
    if token not in bench: fail(f'benchmark state-machine mechanism missing: {token}')
if bench.index("rollback_transaction(session.transactionId,'benchmark-complete')")>bench.index('reward=(c1-c0)/c0'): fail('benchmark reward computed before rollback verification')
for unsafe_refusal in ['exact-qdisc-restore-not-proven','no-generic-third-party-sfe-contract']:
    if unsafe_refusal not in core: fail(f'explicit unsafe-provider refusal missing: {unsafe_refusal}')

# Rill boundary, persistence and bounded storage.
# Rill is an EXTERNAL runtime: this repository never compiles or natively tests
# it, so there is deliberately no bundled Rust source and no Rust build path.
rill_mk=(ROOT/'package/performance-manager-rill/Makefile').read_text(); rill_init=(ROOT/'package/performance-manager-rill/files/etc/init.d/performance-manager-rill').read_text()
if (ROOT/'package/performance-manager-rill/src').exists(): fail('bundled Rill source must not exist (external runtime)')
for token in ['rust/host','rust-package.mk','RUST_PKG_LOCKED:=1','cargo']:
    if token in rill_mk: fail(f'Rill build invariant must NOT be present (external runtime): {token}')
# The integration package still guards the external runtime and stays fail-closed.
for token in ['Build/Compile','PKG_BUILD_DEPENDS:=']:
    if token not in rill_mk: fail(f'integration Makefile mechanism missing: {token}')
for token in ['resolve_binary','BINARY_STATE=','binary-invalid','external Rill runtime not provisioned','--state-dir "$state_dir"','procd_set_param user "$SERVICE_USER"','chmod 0750']:
    if token not in rill_init: fail(f'Rill integration-guard invariant missing: {token}')
for token in ["const RILL_REQUIRED_OPS = [ 'status', 'observe', 'outcome' ]","const RILL_CONTRACT = 'pm-rill-shadow'","const RILL_PROTOCOL_VERSION = 1","contract-mismatch","protocol-version-mismatch","binary-invalid","external-runtime-not-provisioned","state: RILL_STATES.incompatible"]:
    if token not in core: fail(f'Core Rill capability/protocol gate mechanism missing: {token}')

companion=(ROOT/'companion/pm_companion_agent.py').read_text()
for token in ['pm-companion/v2','shell=False','routerMutation','sessionId','capabilityHash','routeIdentity']:
    if token not in companion: fail(f'Companion v2 boundary missing: {token}')
for token in ['shell=True','uci set','/proc/sys','nft ','iptables']:
    if token in companion: fail(f'Companion mutation primitive forbidden: {token}')

# LuCI required surfaces + full literal zh_Hans coverage.
for page in ['overview','optimize','benchmark','capabilities','rill','history','advanced','settings']:
    if not (ROOT/f'package/luci-app-performance-manager/htdocs/luci-static/resources/view/performance-manager/{page}.js').exists(): fail(f'LuCI page missing: {page}')
po=(ROOT/'package/luci-app-performance-manager/po/zh_Hans/performance-manager.po').read_text()
po_ids=set(re.findall(r'^msgid "(.*)"$',po,re.M)); js_ids=set()
for p in (ROOT/'package/luci-app-performance-manager/htdocs/luci-static/resources').rglob('*.js'):
    for m in re.finditer(r"_\('((?:\\.|[^'\\])*)'\)",p.read_text()):
        try: js_ids.add(ast.literal_eval("'"+m.group(1)+"'"))
        except Exception: js_ids.add(m.group(1))
for msg in sorted(js_ids):
    esc=msg.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n')
    if esc not in po_ids: fail(f'zh_Hans missing msgid: {msg}')

# The recommended all-in-one APK must physically own every application layer;
# it is not allowed to regress into a meta package depending on the split APKs.
bundle=(ROOT/'package/luci-app-performance-manager-all/Makefile').read_text()
for token in ['po2lmo','/usr/sbin/performance-manager.uc','luci-app-performance-manager/htdocs',
              'luci-app-performance-manager/root/usr/share/rpcd','performance-manager-rill/files',
              '/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo']:
    if token not in bundle: fail(f'all-in-one physical payload mechanism missing: {token}')
bundle_pkg=re.search(r'define Package/luci-app-performance-manager-all\n(.*?)\nendef',bundle,re.S)
if not bundle_pkg: fail('all-in-one package definition missing')
else:
    for forbidden in ['+performance-manager ', '+luci-app-performance-manager', '+performance-manager-rill']:
        if forbidden in bundle_pkg.group(1): fail(f'all-in-one meta dependency forbidden: {forbidden}')
    for conflict in ['performance-manager','luci-app-performance-manager',
                     'luci-i18n-performance-manager-zh-cn','performance-manager-rill']:
        if conflict not in bundle_pkg.group(1): fail(f'all-in-one split-owner conflict missing: {conflict}')
if 'PROVIDES:=' in bundle: fail('all-in-one must not alias split package names through APK PROVIDES')

# Scan only the repository's own files.  In CI the workspace also contains the
# downloaded OpenWrt SDK tree (a subdirectory whose feeds legitimately include
# filenames like ".../0024-spi-pl022-Prompt-warning-....patch"); those must not
# count as this repository shipping a prompt artifact, so walk git-tracked
# files (the SDK tree is untracked), falling back to the on-disk walk when git
# is unavailable.
try:
    import subprocess
    _out = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, text=True)
    _tracked = [ROOT / p for p in _out.stdout.split('\0') if p]
except Exception:
    _tracked = [p for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and '.git' not in p.parts]
for p in _tracked:
    if p.is_file() and ('提示词' in p.name or re.search(r'(^|[_-])prompt([_.-]|$)', p.name, re.I)):
        fail(f'prompt artifact must not ship: {p.relative_to(ROOT)}')
if errors:
    print(f'CONTRACT VALIDATION FAILED ({len(errors)})'); [print(' -',e) for e in errors]; sys.exit(1)
print(f'CONTRACT VALIDATION PASSED: {len(profiles)} profiles, {len(pairs)} schema examples, {len(required_ubus)} ubus methods, full zh_Hans literal coverage')
