#!/bin/sh
# Stable resource/write evidence for a booted OpenWrt target with exact Rill.
# Missing measurements are BLOCKED; they are never rewritten as numeric zero.
set -eu

DURATION="${PM_SOAK_SECONDS:-86400}"
INTERVAL="${PM_SOAK_INTERVAL:-60}"
OUT="${PM_EVIDENCE_OUT:-/tmp/performance-manager-resource-soak.json}"
RILL_STATE_DIR="${PM_RILL_STATE_DIR:-/etc/performance-manager/rill}"
PM_COMMIT_SHA="${PM_COMMIT_SHA:-unknown}"
case "$DURATION:$INTERVAL" in *[!0-9:]*|:*) echo 'invalid duration/interval' >&2; exit 2;; esac
[ "$DURATION" -gt 0 ] && [ "$INTERVAL" -gt 0 ] || exit 2
command -v jsonfilter >/dev/null 2>&1 || { echo 'jsonfilter required' >&2; exit 1; }

# Precommitted before Stable execution; mirrored in docs/RESOURCE_BUDGET.json.
B_CORE_RSS=65536
B_RILL_RSS=98304
B_CORE_CPU=5.0
B_RILL_CPU=5.0
B_CORE_RESTARTS=0
B_RILL_RESTARTS=0
B_PM_WRITES_DAY=32
B_IDLE_OBSERVES=0
B_IDLE_PERSISTENCE=0
B_RILL_STATE_BYTES=4194304
B_BINDINGS=64
B_HISTORY_GROWTH=262144

jget() { printf '%s\n' "$1" | jsonfilter -e "$2" 2>/dev/null || true; }
is_uint() { case "$1" in ''|*[!0-9]*) return 1;; *) return 0;; esac; }
ticks() { awk '{print $14+$15}' "/proc/$1/stat" 2>/dev/null || true; }
rss() { awk '/^VmRSS:/ {print $2}' "/proc/$1/status" 2>/dev/null || true; }
rill_pid() { pidof rill-pm-adapter 2>/dev/null | awk '{print $1}'; }
state_max() {
  max=0
  for file in "$RILL_STATE_DIR"/*; do
    [ -f "$file" ] || continue
    size=$(stat -c '%s' "$file" 2>/dev/null || busybox stat -c '%s' "$file" 2>/dev/null || true)
    is_uint "$size" || continue
    [ "$size" -gt "$max" ] && max="$size"
  done
  printf '%s\n' "$max"
}
blocked() {
  reason="$1"
  cat >"$OUT" <<EOF_JSON
{
  "schemaVersion": 2,
  "gate": "resource-soak",
  "pmCommitSha": "$PM_COMMIT_SHA",
  "verdict": "BLOCKED",
  "measurementUnavailable": "$reason",
  "durationSeconds": 0,
  "stableDurationSatisfied": false,
  "passed": false
}
EOF_JSON
  printf 'BLOCKED: %s\nEvidence: %s\n' "$reason" "$OUT" >&2
  exit 1
}

D0=$(ubus call performance-manager diagnostics '{}' 2>/dev/null || true)
[ -n "$D0" ] || blocked core-diagnostics-unavailable
core_pid=$(jget "$D0" '@.resources.corePid')
rill_pid_now=$(rill_pid)
is_uint "$core_pid" || blocked core-pid-unavailable
is_uint "$rill_pid_now" || blocked rill-pid-unavailable
[ -r "/proc/$core_pid/stat" ] || blocked core-process-unavailable
[ -r "/proc/$rill_pid_now/stat" ] || blocked rill-process-unavailable
rill_exe=$(readlink -f "/proc/$rill_pid_now/exe" 2>/dev/null || true)
[ -n "$rill_exe" ] && [ -r "$rill_exe" ] || blocked rill-executable-unavailable
adapter_sha=$(sha256sum "$rill_exe" 2>/dev/null | awk '{print $1}')
[ -n "$adapter_sha" ] || blocked rill-adapter-sha-unavailable

core_w0=$(jget "$D0" '@.resources.corePersistentWritesSinceStart')
obs0=$(jget "$D0" '@.resources.rillCounters.rillObserveAccepted')
out0=$(jget "$D0" '@.resources.rillCounters.rillOutcomeAccepted')
persist0=$(jget "$D0" '@.resources.rillCounters.expectedAdapterPersistenceEvents')
binding0=$(jget "$D0" '@.resources.rillCounters.rillBindingHighWater')
history0=$(jget "$D0" '@.resources.persistentHistoryBytes')
journal_files0=$(jget "$D0" '@.resources.rillExecutionHealth.journalFileCount')
journal_bytes0=$(jget "$D0" '@.resources.rillExecutionHealth.journalBytes')
retired0=$(jget "$D0" '@.resources.rillExecutionHealth.retired')
intervention0=$(jget "$D0" '@.resources.rillExecutionHealth.interventionRequiredCount')
active0=$(jget "$D0" '@.resources.rillExecutionHealth.active')
executing0=$(jget "$D0" '@.resources.rillExecutionHealth.executing')
for pair in "core-writes:$core_w0" "observe:$obs0" "outcome:$out0" \
            "adapter-persistence:$persist0" "binding-high-water:$binding0" "history:$history0" \
            "journal-files:$journal_files0" "journal-bytes:$journal_bytes0" "retired:$retired0" \
            "intervention:$intervention0" "active:$active0" "executing:$executing0"; do
  name=${pair%%:*}; value=${pair#*:}; is_uint "$value" || blocked "$name-measurement-unavailable"
done

start_epoch=$(date +%s)
clk=$(getconf CLK_TCK 2>/dev/null || echo 100)
is_uint "$clk" || blocked clock-tick-measurement-unavailable
core_last_ticks=$(ticks "$core_pid"); rill_last_ticks=$(ticks "$rill_pid_now")
is_uint "$core_last_ticks" || blocked core-cpu-measurement-unavailable
is_uint "$rill_last_ticks" || blocked rill-cpu-measurement-unavailable
core_ticks_total=0; rill_ticks_total=0
core_max_rss=0; rill_max_rss=0; rill_state_max=0
core_restarts=0; rill_restarts=0; samples=0

while :; do
  now=$(date +%s); elapsed=$((now-start_epoch)); [ "$elapsed" -ge "$DURATION" ] && break
  current_core=$(jget "$(ubus call performance-manager diagnostics '{}' 2>/dev/null || true)" '@.resources.corePid')
  current_rill=$(rill_pid)
  is_uint "$current_core" || blocked core-process-exited-during-soak
  is_uint "$current_rill" || blocked rill-process-exited-during-soak
  [ -r "/proc/$current_core/stat" ] || blocked core-process-exited-during-soak
  [ -r "/proc/$current_rill/stat" ] || blocked rill-process-exited-during-soak

  ct=$(ticks "$current_core"); rt=$(ticks "$current_rill")
  cr=$(rss "$current_core"); rr=$(rss "$current_rill")
  is_uint "$ct" && is_uint "$rt" && is_uint "$cr" && is_uint "$rr" || blocked process-metric-unavailable
  if [ "$current_core" = "$core_pid" ]; then core_ticks_total=$((core_ticks_total+ct-core_last_ticks)); else core_restarts=$((core_restarts+1)); core_pid="$current_core"; fi
  if [ "$current_rill" = "$rill_pid_now" ]; then rill_ticks_total=$((rill_ticks_total+rt-rill_last_ticks)); else rill_restarts=$((rill_restarts+1)); rill_pid_now="$current_rill"; fi
  core_last_ticks="$ct"; rill_last_ticks="$rt"
  [ "$cr" -gt "$core_max_rss" ] && core_max_rss="$cr"
  [ "$rr" -gt "$rill_max_rss" ] && rill_max_rss="$rr"
  sm=$(state_max); [ "$sm" -gt "$rill_state_max" ] && rill_state_max="$sm"
  samples=$((samples+1))
  sleep "$INTERVAL"
done

end_epoch=$(date +%s); elapsed=$((end_epoch-start_epoch))
D1=$(ubus call performance-manager diagnostics '{}' 2>/dev/null || true)
[ -n "$D1" ] || blocked final-core-diagnostics-unavailable
core_w1=$(jget "$D1" '@.resources.corePersistentWritesSinceStart')
obs1=$(jget "$D1" '@.resources.rillCounters.rillObserveAccepted')
out1=$(jget "$D1" '@.resources.rillCounters.rillOutcomeAccepted')
persist1=$(jget "$D1" '@.resources.rillCounters.expectedAdapterPersistenceEvents')
binding1=$(jget "$D1" '@.resources.rillCounters.rillBindingHighWater')
history1=$(jget "$D1" '@.resources.persistentHistoryBytes')
journal_files1=$(jget "$D1" '@.resources.rillExecutionHealth.journalFileCount')
journal_bytes1=$(jget "$D1" '@.resources.rillExecutionHealth.journalBytes')
retired1=$(jget "$D1" '@.resources.rillExecutionHealth.retired')
intervention1=$(jget "$D1" '@.resources.rillExecutionHealth.interventionRequiredCount')
active1=$(jget "$D1" '@.resources.rillExecutionHealth.active')
executing1=$(jget "$D1" '@.resources.rillExecutionHealth.executing')
for pair in "core-writes:$core_w1" "observe:$obs1" "outcome:$out1" \
            "adapter-persistence:$persist1" "binding-high-water:$binding1" "history:$history1" \
            "journal-files:$journal_files1" "journal-bytes:$journal_bytes1" "retired:$retired1" \
            "intervention:$intervention1" "active:$active1" "executing:$executing1"; do
  name=${pair%%:*}; value=${pair#*:}; is_uint "$value" || blocked "final-$name-measurement-unavailable"
done

core_delta=$((core_w1-core_w0)); obs_delta=$((obs1-obs0)); out_delta=$((out1-out0))
persist_delta=$((persist1-persist0)); history_growth=$((history1-history0))
[ "$core_delta" -ge 0 ] && [ "$obs_delta" -ge 0 ] && [ "$out_delta" -ge 0 ] \
  && [ "$persist_delta" -ge 0 ] && [ "$history_growth" -ge 0 ] || blocked counter-reset-during-soak
[ "$binding1" -gt "$binding0" ] && binding_high="$binding1" || binding_high="$binding0"
[ "$journal_files1" -ge 0 ] && [ "$journal_bytes1" -ge 0 ] && [ "$retired1" -ge 0 ] || blocked journal-measurement-invalid
[ "$intervention1" -ge 0 ] && [ "$active1" -ge 0 ] && [ "$executing1" -ge 0 ] || blocked execution-health-measurement-invalid
cpu_core=$(awk -v t="$core_ticks_total" -v hz="$clk" -v s="$elapsed" 'BEGIN { if (s<=0||hz<=0) print "0.000"; else printf "%.3f", (t/hz)/s*100 }')
cpu_rill=$(awk -v t="$rill_ticks_total" -v hz="$clk" -v s="$elapsed" 'BEGIN { if (s<=0||hz<=0) print "0.000"; else printf "%.3f", (t/hz)/s*100 }')
writes_day=$(awk -v w="$core_delta" -v s="$elapsed" 'BEGIN { if (s<=0) print "0.0"; else printf "%.1f", w*86400/s }')
stable=$([ "$elapsed" -ge 86400 ] && printf true || printf false)

within=true
[ "$core_max_rss" -le "$B_CORE_RSS" ] || within=false
[ "$rill_max_rss" -le "$B_RILL_RSS" ] || within=false
awk -v x="$cpu_core" -v b="$B_CORE_CPU" 'BEGIN { exit !(x<=b) }' || within=false
awk -v x="$cpu_rill" -v b="$B_RILL_CPU" 'BEGIN { exit !(x<=b) }' || within=false
[ "$core_restarts" -le "$B_CORE_RESTARTS" ] || within=false
[ "$rill_restarts" -le "$B_RILL_RESTARTS" ] || within=false
awk -v x="$writes_day" -v b="$B_PM_WRITES_DAY" 'BEGIN { exit !(x<=b) }' || within=false
[ "$obs_delta" -le "$B_IDLE_OBSERVES" ] || within=false
[ "$persist_delta" -le "$B_IDLE_PERSISTENCE" ] || within=false
[ "$rill_state_max" -le "$B_RILL_STATE_BYTES" ] || within=false
[ "$binding_high" -le "$B_BINDINGS" ] || within=false
[ "$history_growth" -le "$B_HISTORY_GROWTH" ] || within=false
[ "$journal_files1" -le 128 ] || within=false
[ "$journal_bytes1" -le 2097152 ] || within=false
[ "$retired1" -le 64 ] || within=false
[ "$intervention1" = 0 ] || within=false
[ "$stable" = true ] || within=false

cat >"$OUT" <<EOF_JSON
{
  "schemaVersion": 2,
  "gate": "resource-soak",
  "pmCommitSha": "$PM_COMMIT_SHA",
  "adapterSha256": "$adapter_sha",
  "verdict": "$([ "$within" = true ] && printf PASS || printf FAIL)",
  "durationSeconds": $elapsed,
  "sampleCount": $samples,
  "rillPresentAndRunning": true,
  "coreMaxRssKiB": $core_max_rss,
  "coreMeanCpuPercentApprox": $cpu_core,
  "rillMaxRssKiB": $rill_max_rss,
  "rillMeanCpuPercentApprox": $cpu_rill,
  "coreRestartCount": $core_restarts,
  "rillRestartCount": $rill_restarts,
  "pmPersistentWrites": $core_delta,
  "pmPersistentWritesPerDayApprox": $writes_day,
  "rillObserveAcceptedDelta": $obs_delta,
  "rillOutcomeAcceptedDelta": $out_delta,
  "expectedAdapterPersistenceEventsDelta": $persist_delta,
  "persistenceAccounting": "logical/inferred-from-pinned-rill-contract",
  "rillStateMaxFileBytes": $rill_state_max,
  "bindingHighWater": $binding_high,
  "persistentHistoryGrowthBytes": $history_growth,
  "executionJournalFileCount": $journal_files1,
  "executionJournalBytes": $journal_bytes1,
  "retiredExecutionCount": $retired1,
  "interventionRequiredCount": $intervention1,
  "activeExecutionCount": $active1,
  "executingExecutionCount": $executing1,
  "stableDurationSatisfied": $stable,
  "measurementUnavailable": null,
  "budgets": {
    "coreMaxRssKiB": $B_CORE_RSS,
    "rillMaxRssKiB": $B_RILL_RSS,
    "coreMeanCpuPercent": $B_CORE_CPU,
    "rillMeanCpuPercent": $B_RILL_CPU,
    "coreRestartCount": $B_CORE_RESTARTS,
    "rillRestartCount": $B_RILL_RESTARTS,
    "pmPersistentWritesPerDay": $B_PM_WRITES_DAY,
    "idleRillObserveAcceptedDelta": $B_IDLE_OBSERVES,
    "idleExpectedAdapterPersistenceEventsDelta": $B_IDLE_PERSISTENCE,
    "rillStateFileMaxBytes": $B_RILL_STATE_BYTES,
    "bindingHighWater": $B_BINDINGS,
    "persistentHistoryGrowthBytes": $B_HISTORY_GROWTH
  },
  "passed": $within
}
EOF_JSON
printf 'Evidence: %s\n' "$OUT"
[ "$within" = true ]
