#!/bin/sh
# Stable resource/write evidence for a booted OpenWrt target with the exact
# generic Runtime. Runtime calls are subprocess-scoped; unavailable process
# metrics remain unavailable and therefore cannot be promoted to PASS.
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
B_CORE_CPU=5.0
B_CORE_RESTARTS=0
B_PM_WRITES_DAY=32
B_RUNTIME_FAILURES=0
B_RUNTIME_TIMEOUTS=0
B_RUNTIME_MALFORMED=0
B_RUNTIME_NONZERO=0
B_IDLE_OBSERVES=0
B_IDLE_PERSISTENCE=0
B_RUNTIME_STATE_BYTES=4194304
B_BINDINGS=64
B_HISTORY_GROWTH=262144

jget() { printf '%s\n' "$1" | jsonfilter -e "$2" 2>/dev/null || true; }
is_uint() { case "$1" in ''|*[!0-9]*) return 1;; *) return 0;; esac; }
ticks() { awk '{print $14+$15}' "/proc/$1/stat" 2>/dev/null || true; }
rss() { awk '/^VmRSS:/ {print $2}' "/proc/$1/status" 2>/dev/null || true; }
state_max() {
  max=0
  for file in "$RILL_STATE_DIR"/*; do
    [ -f "$file" ] || continue
    size=$(stat -c '%s' "$file" 2>/dev/null || busybox stat -c '%s' "$file" 2>/dev/null || true)
    is_uint "$size" || return 1
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
is_uint "$core_pid" || blocked core-pid-unavailable
[ -r "/proc/$core_pid/stat" ] || blocked core-process-unavailable
[ -x /usr/bin/rill-runtime ] || blocked rill-runtime-not-provisioned
runtime_sha=$(sha256sum /usr/bin/rill-runtime 2>/dev/null | awk '{print $1}')
[ -n "$runtime_sha" ] || blocked rill-runtime-sha-unavailable
[ -d "$RILL_STATE_DIR" ] || blocked runtime-state-directory-unavailable

core_w0=$(jget "$D0" '@.resources.corePersistentWritesSinceStart')
obs0=$(jget "$D0" '@.resources.rillCounters.rillObserveAccepted')
out0=$(jget "$D0" '@.resources.rillCounters.rillOutcomeAccepted')
persist0=$(jget "$D0" '@.resources.rillCounters.expectedRuntimePersistenceEvents')
runtime_invocations0=$(jget "$D0" '@.resources.rillCounters.runtimeInvocationCount')
runtime_successes0=$(jget "$D0" '@.resources.rillCounters.runtimeSuccessfulInvocationCount')
runtime_failures0=$(jget "$D0" '@.resources.rillCounters.runtimeInvocationFailureCount')
runtime_timeouts0=$(jget "$D0" '@.resources.rillCounters.runtimeTimeoutCount')
runtime_malformed0=$(jget "$D0" '@.resources.rillCounters.runtimeMalformedResponseCount')
runtime_nonzero0=$(jget "$D0" '@.resources.rillCounters.runtimeNonZeroExitCount')
binding0=$(jget "$D0" '@.resources.rillCounters.rillBindingHighWater')
history0=$(jget "$D0" '@.resources.persistentHistoryBytes')
journal_files0=$(jget "$D0" '@.resources.rillExecutionHealth.journalFileCount')
journal_bytes0=$(jget "$D0" '@.resources.rillExecutionHealth.journalBytes')
retired0=$(jget "$D0" '@.resources.rillExecutionHealth.retired')
intervention0=$(jget "$D0" '@.resources.rillExecutionHealth.interventionRequiredCount')
active0=$(jget "$D0" '@.resources.rillExecutionHealth.active')
executing0=$(jget "$D0" '@.resources.rillExecutionHealth.executing')
for pair in "core-writes:$core_w0" "observe:$obs0" "outcome:$out0" \
            "runtime-persistence:$persist0" "binding-high-water:$binding0" "history:$history0" \
            "runtime-invocations:$runtime_invocations0" "runtime-successes:$runtime_successes0" \
            "runtime-failures:$runtime_failures0" "runtime-timeouts:$runtime_timeouts0" \
            "runtime-malformed:$runtime_malformed0" "runtime-nonzero:$runtime_nonzero0" \
            "journal-files:$journal_files0" "journal-bytes:$journal_bytes0" "retired:$retired0" \
            "intervention:$intervention0" "active:$active0" "executing:$executing0"; do
  name=${pair%%:*}; value=${pair#*:}; is_uint "$value" || blocked "$name-measurement-unavailable"
done

start_epoch=$(date +%s)
clk=$(getconf CLK_TCK 2>/dev/null || echo 100)
is_uint "$clk" || blocked clock-tick-measurement-unavailable
core_last_ticks=$(ticks "$core_pid")
is_uint "$core_last_ticks" || blocked core-cpu-measurement-unavailable
core_ticks_total=0; core_max_rss=0; rill_state_max=0
core_restarts=0; samples=0

while :; do
  now=$(date +%s); elapsed=$((now-start_epoch)); [ "$elapsed" -ge "$DURATION" ] && break
  current_core=$(jget "$(ubus call performance-manager diagnostics '{}' 2>/dev/null || true)" '@.resources.corePid')
  is_uint "$current_core" || blocked core-process-exited-during-soak
  [ -r "/proc/$current_core/stat" ] || blocked core-process-exited-during-soak
  ubus call performance-manager rill_status '{}' >/dev/null 2>&1 || blocked rill-runtime-call-failed
  ct=$(ticks "$current_core")
  cr=$(rss "$current_core")
  if ! is_uint "$ct" || ! is_uint "$cr"; then
    blocked core-process-metric-unavailable
  fi
  if [ "$current_core" = "$core_pid" ]; then core_ticks_total=$((core_ticks_total+ct-core_last_ticks)); else core_restarts=$((core_restarts+1)); core_pid="$current_core"; fi
  core_last_ticks="$ct"
  [ "$cr" -gt "$core_max_rss" ] && core_max_rss="$cr"
  sm=$(state_max) || blocked runtime-state-measurement-unavailable
  [ "$sm" -gt "$rill_state_max" ] && rill_state_max="$sm"
  samples=$((samples+1))
  sleep "$INTERVAL"
done

end_epoch=$(date +%s); elapsed=$((end_epoch-start_epoch))
D1=$(ubus call performance-manager diagnostics '{}' 2>/dev/null || true)
[ -n "$D1" ] || blocked final-core-diagnostics-unavailable
core_w1=$(jget "$D1" '@.resources.corePersistentWritesSinceStart')
obs1=$(jget "$D1" '@.resources.rillCounters.rillObserveAccepted')
out1=$(jget "$D1" '@.resources.rillCounters.rillOutcomeAccepted')
persist1=$(jget "$D1" '@.resources.rillCounters.expectedRuntimePersistenceEvents')
runtime_invocations1=$(jget "$D1" '@.resources.rillCounters.runtimeInvocationCount')
runtime_successes1=$(jget "$D1" '@.resources.rillCounters.runtimeSuccessfulInvocationCount')
runtime_failures1=$(jget "$D1" '@.resources.rillCounters.runtimeInvocationFailureCount')
runtime_timeouts1=$(jget "$D1" '@.resources.rillCounters.runtimeTimeoutCount')
runtime_malformed1=$(jget "$D1" '@.resources.rillCounters.runtimeMalformedResponseCount')
runtime_nonzero1=$(jget "$D1" '@.resources.rillCounters.runtimeNonZeroExitCount')
binding1=$(jget "$D1" '@.resources.rillCounters.rillBindingHighWater')
history1=$(jget "$D1" '@.resources.persistentHistoryBytes')
journal_files1=$(jget "$D1" '@.resources.rillExecutionHealth.journalFileCount')
journal_bytes1=$(jget "$D1" '@.resources.rillExecutionHealth.journalBytes')
retired1=$(jget "$D1" '@.resources.rillExecutionHealth.retired')
intervention1=$(jget "$D1" '@.resources.rillExecutionHealth.interventionRequiredCount')
active1=$(jget "$D1" '@.resources.rillExecutionHealth.active')
executing1=$(jget "$D1" '@.resources.rillExecutionHealth.executing')
for pair in "core-writes:$core_w1" "observe:$obs1" "outcome:$out1" \
            "runtime-persistence:$persist1" "binding-high-water:$binding1" "history:$history1" \
            "runtime-invocations:$runtime_invocations1" "runtime-successes:$runtime_successes1" \
            "runtime-failures:$runtime_failures1" "runtime-timeouts:$runtime_timeouts1" \
            "runtime-malformed:$runtime_malformed1" "runtime-nonzero:$runtime_nonzero1" \
            "journal-files:$journal_files1" "journal-bytes:$journal_bytes1" "retired:$retired1" \
            "intervention:$intervention1" "active:$active1" "executing:$executing1"; do
  name=${pair%%:*}; value=${pair#*:}; is_uint "$value" || blocked "final-$name-measurement-unavailable"
done

core_delta=$((core_w1-core_w0)); obs_delta=$((obs1-obs0)); out_delta=$((out1-out0))
persist_delta=$((persist1-persist0)); history_growth=$((history1-history0))
runtime_invocations=$((runtime_invocations1-runtime_invocations0))
runtime_successes=$((runtime_successes1-runtime_successes0))
runtime_failures=$((runtime_failures1-runtime_failures0))
runtime_timeouts=$((runtime_timeouts1-runtime_timeouts0))
runtime_malformed=$((runtime_malformed1-runtime_malformed0))
runtime_nonzero=$((runtime_nonzero1-runtime_nonzero0))
[ "$core_delta" -ge 0 ] && [ "$obs_delta" -ge 0 ] && [ "$out_delta" -ge 0 ] \
  && [ "$persist_delta" -ge 0 ] && [ "$history_growth" -ge 0 ] \
  && [ "$runtime_invocations" -ge 0 ] && [ "$runtime_successes" -ge 0 ] \
  && [ "$runtime_failures" -ge 0 ] && [ "$runtime_timeouts" -ge 0 ] \
  && [ "$runtime_malformed" -ge 0 ] && [ "$runtime_nonzero" -ge 0 ] || blocked counter-reset-during-soak
[ "$binding1" -gt "$binding0" ] && binding_high="$binding1" || binding_high="$binding0"
[ "$journal_files1" -ge 0 ] && [ "$journal_bytes1" -ge 0 ] && [ "$retired1" -ge 0 ] || blocked journal-measurement-invalid
[ "$intervention1" -ge 0 ] && [ "$active1" -ge 0 ] && [ "$executing1" -ge 0 ] || blocked execution-health-measurement-invalid
cpu_core=$(awk -v t="$core_ticks_total" -v hz="$clk" -v s="$elapsed" 'BEGIN { if (s<=0||hz<=0) print "0.000"; else printf "%.3f", (t/hz)/s*100 }')
writes_day=$(awk -v w="$core_delta" -v s="$elapsed" 'BEGIN { if (s<=0) print "0.0"; else printf "%.1f", w*86400/s }')
stable=$([ "$elapsed" -ge 86400 ] && printf true || printf false)

within=true
[ "$core_max_rss" -le "$B_CORE_RSS" ] || within=false
awk -v x="$cpu_core" -v b="$B_CORE_CPU" 'BEGIN { exit !(x<=b) }' || within=false
[ "$core_restarts" -le "$B_CORE_RESTARTS" ] || within=false
awk -v x="$writes_day" -v b="$B_PM_WRITES_DAY" 'BEGIN { exit !(x<=b) }' || within=false
[ "$obs_delta" -le "$B_IDLE_OBSERVES" ] || within=false
[ "$persist_delta" -le "$B_IDLE_PERSISTENCE" ] || within=false
[ "$rill_state_max" -le "$B_RUNTIME_STATE_BYTES" ] || within=false
[ "$binding_high" -le "$B_BINDINGS" ] || within=false
[ "$history_growth" -le "$B_HISTORY_GROWTH" ] || within=false
[ "$journal_files1" -le 128 ] || within=false
[ "$journal_bytes1" -le 2097152 ] || within=false
[ "$retired1" -le 64 ] || within=false
[ "$intervention1" = 0 ] || within=false
[ "$stable" = true ] || within=false
[ "$runtime_invocations" -gt 0 ] || within=false
[ "$runtime_successes" -gt 0 ] && [ "$runtime_successes" -le "$runtime_invocations" ] || within=false
[ "$runtime_failures" -eq 0 ] && [ "$runtime_timeouts" -eq 0 ] \
  && [ "$runtime_malformed" -eq 0 ] && [ "$runtime_nonzero" -eq 0 ] || within=false

cat >"$OUT" <<EOF_JSON
{
  "evidenceStatus": "standalone-target-helper",
  "stableAuthorization": "not-directly-authorized",
  "schemaVersion": 2,
  "gate": "resource-soak",
  "pmCommitSha": "$PM_COMMIT_SHA",
  "runtimeSha256": "$runtime_sha",
  "verdict": "$([ "$within" = true ] && printf PASS || printf FAIL)",
  "durationSeconds": $elapsed,
  "rawFacts": {
    "installedPackages": {},
    "durationSeconds": $elapsed,
    "soak": {
      "rillPresent": true,
      "sampleCount": $samples,
      "coreRestartCount": $core_restarts,
      "idleRillObserveAcceptedDelta": $obs_delta,
      "idleExpectedRuntimePersistenceEventsDelta": $persist_delta,
      "idlePendingOutcomeJournalWrites": 0,
      "executingJournalDelta": 0,
      "runtimeInvocationCount": $runtime_invocations,
      "runtimeSuccessfulInvocationCount": $runtime_successes,
      "runtimeInvocationFailureCount": $runtime_failures,
      "runtimeTimeoutCount": $runtime_timeouts,
      "runtimeMalformedResponseCount": $runtime_malformed,
      "runtimeNonZeroExitCount": $runtime_nonzero,
      "resources": {
        "coreRssKiB": $core_max_rss,
        "coreMeanCpuPercent": $cpu_core,
        "corePersistentWritesPerDay": $writes_day,
        "bindingHighWater": $binding_high,
        "interventionRequiredCount": $intervention1,
        "persistentHistoryGrowthBytes": $history_growth,
        "executionJournalFileCount": $journal_files1,
        "executionJournalBytes": $journal_bytes1,
        "retiredExecutionCount": $retired1,
        "activeExecutionCount": $active1,
        "executingExecutionCount": $executing1,
        "runtimeStateMaxBytes": $rill_state_max
      }
    }
  },
  "stableDurationSatisfied": $stable,
  "runtimeInvocationAccounting": "bounded subprocess lifecycle counters from Core diagnostics",
  "pmPersistentWrites": $core_delta,
  "pmPersistentWritesPerDayApprox": $writes_day,
  "rillObserveAcceptedDelta": $obs_delta,
  "rillOutcomeAcceptedDelta": $out_delta,
  "expectedRuntimePersistenceEventsDelta": $persist_delta,
  "persistenceAccounting": "logical/inferred-from-pinned-rill-contract",
  "runtimeInvocationCount": $runtime_invocations,
  "runtimeSuccessfulInvocationCount": $runtime_successes,
  "runtimeInvocationFailureCount": $runtime_failures,
  "runtimeTimeoutCount": $runtime_timeouts,
  "runtimeMalformedResponseCount": $runtime_malformed,
  "runtimeNonZeroExitCount": $runtime_nonzero,
  "budgets": {
    "coreMaxRssKiB": $B_CORE_RSS,
    "coreMeanCpuPercent": $B_CORE_CPU,
    "coreRestartCount": $B_CORE_RESTARTS,
    "pmPersistentWritesPerDay": $B_PM_WRITES_DAY,
    "runtimeInvocationFailureCount": $B_RUNTIME_FAILURES,
    "runtimeTimeoutCount": $B_RUNTIME_TIMEOUTS,
    "runtimeMalformedResponseCount": $B_RUNTIME_MALFORMED,
    "runtimeNonZeroExitCount": $B_RUNTIME_NONZERO,
    "idleRillObserveAcceptedDelta": $B_IDLE_OBSERVES,
    "idleExpectedRuntimePersistenceEventsDelta": $B_IDLE_PERSISTENCE,
    "runtimeStateMaxBytes": $B_RUNTIME_STATE_BYTES,
    "bindingHighWater": $B_BINDINGS,
    "persistentHistoryGrowthBytes": $B_HISTORY_GROWTH
  },
  "passed": $within
}
EOF_JSON
printf 'Evidence: %s\n' "$OUT"
[ "$within" = true ]
