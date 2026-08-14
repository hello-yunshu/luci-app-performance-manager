#!/bin/sh
# Long-run resource/write evidence. Run on a booted OpenWrt target.
# Defaults to the frozen 24h+ Stable gate; PM_SOAK_SECONDS can be shortened for
# development checks, but such a result is not Stable evidence.
set -eu
DURATION="${PM_SOAK_SECONDS:-86400}"
INTERVAL="${PM_SOAK_INTERVAL:-60}"
OUT="${PM_EVIDENCE_OUT:-/tmp/performance-manager-resource-soak.json}"
case "$DURATION:$INTERVAL" in *[!0-9:]*|:*) echo 'invalid duration/interval' >&2; exit 2;; esac
[ "$DURATION" -gt 0 ] && [ "$INTERVAL" -gt 0 ] || exit 2
command -v jsonfilter >/dev/null 2>&1 || { echo 'jsonfilter required' >&2; exit 1; }

start_epoch=$(date +%s)
clk=$(getconf CLK_TCK 2>/dev/null || echo 100)
max_rss=0
samples=0
D0=$(ubus call performance-manager diagnostics '{}')
pid=$(printf '%s\n' "$D0" | jsonfilter -e '@.resources.corePid' 2>/dev/null || true)
case "$pid" in ''|*[!0-9]*) echo 'Core PID unavailable from diagnostics' >&2; exit 1;; esac
[ -r "/proc/$pid/stat" ] || { echo 'performance-manager.uc not running' >&2; exit 1; }
start_ticks=$(awk '{print $14+$15}' "/proc/$pid/stat")
core_w0=$(printf '%s\n' "$D0" | jsonfilter -e '@.resources.corePersistentWritesSinceStart' 2>/dev/null || echo 0)
R0=$(ubus call performance-manager rill_status '{}' 2>/dev/null || printf '{}')
rill_w0=$(printf '%s\n' "$R0" | jsonfilter -e '@.detail.persistentWrites' 2>/dev/null || echo 0)
case "$core_w0" in ''|*[!0-9]*) core_w0=0;; esac
case "$rill_w0" in ''|*[!0-9]*) rill_w0=0;; esac

while :; do
  now=$(date +%s); elapsed=$((now-start_epoch)); [ "$elapsed" -ge "$DURATION" ] && break
  [ -r "/proc/$pid/status" ] || { echo 'Core process exited during soak' >&2; exit 1; }
  rss=$(awk '/^VmRSS:/ {print $2}' "/proc/$pid/status"); rss=${rss:-0}
  [ "$rss" -gt "$max_rss" ] && max_rss=$rss
  samples=$((samples+1))
  sleep "$INTERVAL"
done

end_epoch=$(date +%s); elapsed=$((end_epoch-start_epoch))
end_ticks=$(awk '{print $14+$15}' "/proc/$pid/stat")
D1=$(ubus call performance-manager diagnostics '{}')
core_w1=$(printf '%s\n' "$D1" | jsonfilter -e '@.resources.corePersistentWritesSinceStart' 2>/dev/null || echo 0)
R1=$(ubus call performance-manager rill_status '{}' 2>/dev/null || printf '{}')
rill_w1=$(printf '%s\n' "$R1" | jsonfilter -e '@.detail.persistentWrites' 2>/dev/null || echo 0)
case "$core_w1" in ''|*[!0-9]*) core_w1=0;; esac
case "$rill_w1" in ''|*[!0-9]*) rill_w1=0;; esac
core_delta=$((core_w1-core_w0)); [ "$core_delta" -lt 0 ] && core_delta=0
rill_delta=$((rill_w1-rill_w0)); [ "$rill_delta" -lt 0 ] && rill_delta=0
cpu_ticks=$((end_ticks-start_ticks)); [ "$cpu_ticks" -lt 0 ] && cpu_ticks=0
cpu_pct=$(awk -v t="$cpu_ticks" -v hz="$clk" -v s="$elapsed" 'BEGIN { if (s<=0||hz<=0) print "0.000"; else printf "%.3f", (t/hz)/s*100 }')
writes_day=$(awk -v w="$((core_delta+rill_delta))" -v s="$elapsed" 'BEGIN { if (s<=0) print "0.0"; else printf "%.1f", w*86400/s }')
stable=$([ "$elapsed" -ge 86400 ] && printf true || printf false)

cat >"$OUT" <<EOF_JSON
{
  "schemaVersion": 1,
  "gate": "resource-soak",
  "durationSeconds": $elapsed,
  "sampleCount": $samples,
  "coreMaxRssKiB": $max_rss,
  "coreMeanCpuPercentApprox": $cpu_pct,
  "corePersistentWrites": $core_delta,
  "rillPersistentWrites": $rill_delta,
  "persistentLogicalWritesPerDayApprox": $writes_day,
  "stableDurationSatisfied": $stable,
  "executionPassed": true,
  "passed": $stable
}
EOF_JSON
printf 'Evidence: %s\n' "$OUT"
[ "$stable" = true ]
