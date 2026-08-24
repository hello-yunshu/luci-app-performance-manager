#!/usr/bin/env python3
import argparse,json
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument('--source-tree',default='.'); a=ap.parse_args(); root=Path(a.source_tree).resolve()
areas={}
for name,path,payload_roots in [
    ('core',root/'package/performance-manager',[root/'package/performance-manager/files']),
    ('luci',root/'package/luci-app-performance-manager',[root/'package/luci-app-performance-manager/htdocs',root/'package/luci-app-performance-manager/root',root/'package/luci-app-performance-manager/po']),
    ('rill',root/'package/performance-manager-rill',[root/'package/performance-manager-rill/files']),
    ('allInOne',root/'package/luci-app-performance-manager-all',[]),
]:
    files=[p for p in path.rglob('*') if p.is_file() and '__pycache__' not in p.parts]
    payload=[p for base in payload_roots if base.exists() for p in base.rglob('*') if p.is_file()]
    areas[name]={'files':len(files),'sourceBytes':sum(p.stat().st_size for p in files),'knownStaticPayloadBytes':sum(p.stat().st_size for p in payload)}
report={
 'schemaVersion':2,
 'areas':areas,
 'persistentWritePolicy':{
   'core':'event-only transaction/history/policy intents; fast/deep telemetry remains tmpfs',
   'rill':'Pinned Rill release from contracts/rill-dependency.json persists after every successful Observe and every successful Outcome; its state file is bounded/compacted.',
   'idleInvariant':'Periodic Core telemetry never calls Observe. With no UI/API refresh, benchmark, or configuration/topology event, rillObserveAccepted and expectedAdapterPersistenceEvents must remain unchanged.',
   'accounting':'Core exposes logical counters inferred from the audited pinned Rill contract; these are not physical flash-block write measurements.'
 },
 'limits':{'rillMaxMessageBytes':65536,'rillRequestsPerSecond':20,'rillCoreTimeoutMs':1000,'historyReadTailLines':512,'rillValidatedOutcomeLines':2048,'rillDecisionLedgerLines':4096,'rillStateFileMaxBytes':4194304,'rillBindingCacheEntries':64,'rillExecutionJournalMaxFiles':128,'rillExecutionJournalMaxBytes':2097152,'retiredExecutionRetentionMax':64,'fastTelemetryMinimumSeconds':30,'deepTelemetryMinimumSeconds':300},
 'precommittedStableBudgets':{
   'minimumElapsedSeconds':86400,
   'coreMaxRssKiB':65536,
   'rillMaxRssKiB':98304,
   'coreMeanCpuPercent':5.0,
   'rillMeanCpuPercent':5.0,
   'coreRestartCount':0,
   'rillRestartCount':0,
   'pmPersistentWritesPerDay':32,
   'idleRillObserveAcceptedDelta':0,
   'idleExpectedAdapterPersistenceEventsDelta':0,
   'rillStateFileMaxBytes':4194304,
   'rillExecutionJournalMaxFiles':128,
   'rillExecutionJournalMaxBytes':2097152,
   'retiredExecutionRetentionMax':64,
   'bindingHighWater':64,
   'persistentHistoryGrowthBytes':262144
 },
 'targetRuntimeMetrics':{
   'coreRssKiB':None,'rillRssKiB':None,'coreMeanCpuPercent':None,'rillMeanCpuPercent':None,
   'pmPersistentWritesPerDay':None,'bootStartMilliseconds':None,
   'status':'external-runtime-gate','requiredScripts':['scripts/openwrt-target-gate.sh','scripts/openwrt-resource-soak.sh'],
   'note':'These values require a booted OpenWrt x86_64 target with Rill installed. Missing measurements are BLOCKED/measurementUnavailable, never converted to zero.'
 }
}
out=root/'docs/RESOURCE_BUDGET.json'; out.write_text(json.dumps(report,indent=2)+'\n'); print(json.dumps(report,indent=2))
