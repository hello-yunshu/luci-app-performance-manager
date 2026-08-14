#!/usr/bin/env python3
import argparse,json
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument('--source-tree',default='.'); a=ap.parse_args(); root=Path(a.source_tree).resolve()
areas={}
for name,path,payload_roots in [
    ('core',root/'package/performance-manager',[root/'package/performance-manager/files']),
    ('luci',root/'package/luci-app-performance-manager',[root/'package/luci-app-performance-manager/htdocs',root/'package/luci-app-performance-manager/root',root/'package/luci-app-performance-manager/po']),
    ('rill',root/'package/performance-manager-rill',[root/'package/performance-manager-rill/files']),
]:
    files=[p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    payload=[p for base in payload_roots if base.exists() for p in base.rglob('*') if p.is_file()]
    areas[name]={'files':len(files),'sourceBytes':sum(p.stat().st_size for p in files),'knownStaticPayloadBytes':sum(p.stat().st_size for p in payload)}
report={
 'areas':areas,
 'persistentWritePolicy':{
   'core':'event-only transaction/history/policy intents; fast/deep telemetry remains tmpfs',
   'rill':'validated outcomes + decision-ledger entries for validated outcomes/context drift in /etc/performance-manager/rill; files are bounded/compacted; ordinary observations remain in memory',
   'observationWriteAmplification':'0 persistent writes for ordinary stable-context telemetry observations'
 },
 'limits':{'rillMaxMessageBytes':65536,'rillRequestsPerSecond':20,'rillCoreTimeoutMs':1000,'historyReadTailLines':512,'rillValidatedOutcomeLines':2048,'rillDecisionLedgerLines':4096,'rillStateFileMaxBytes':1048576,'fastTelemetryMinimumSeconds':30,'deepTelemetryMinimumSeconds':300},
 'targetRuntimeMetrics':{
   'rssBytes':None,'steadyCpuPercent':None,'persistentWritesPerDay':None,'bootStartMilliseconds':None,
   'status':'external-runtime-gate','requiredScripts':['scripts/openwrt-target-gate.sh','scripts/openwrt-resource-soak.sh'],
   'note':'These values require a booted OpenWrt x86_64 target. The target gate captures startup/runtime safety evidence; the soak script measures RSS/CPU and Core/Rill logical persistent writes. Values are intentionally not fabricated from source inspection.'
 }
}
out=root/'docs/RESOURCE_BUDGET.json'; out.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))
