#!/bin/sh
# Target-side release evidence gate for a booted OpenWrt 25.12.x x86_64 VM.
# Default is read-only apart from restarting PM/Rill services. Set
# PM_ALLOW_MUTATION=1 only on an explicit test VM to exercise ring apply/rollback
# and ownership cleanup.
set -eu

OUT="${PM_EVIDENCE_OUT:-/tmp/performance-manager-target-gate.json}"
ALLOW_MUTATION="${PM_ALLOW_MUTATION:-0}"
REQUIRE_CORE_ONLY="${PM_REQUIRE_CORE_ONLY:-0}"
PM_COMMIT_SHA="${PM_COMMIT_SHA:-unknown}"
TARGET_PROFILE="${PM_TARGET_PROFILE:-generic}"
failures=""
passes=""
adapter_sha=""

pass() { passes="${passes}${passes:+,}$1"; printf 'PASS: %s\n' "$1"; }
fail() { failures="${failures}${failures:+,}$1"; printf 'FAIL: %s\n' "$1" >&2; }
have() { command -v "$1" >/dev/null 2>&1; }
jget() { printf '%s\n' "$1" | jsonfilter -e "$2" 2>/dev/null || true; }
json_array() {
  oldifs="$IFS"; IFS=','; set -- $1; IFS="$oldifs"
  out='['; first=1
  for v in "$@"; do [ -n "$v" ] || continue; esc=$(printf '%s' "$v" | sed 's/\\/\\\\/g;s/"/\\"/g'); [ "$first" -eq 1 ] || out="$out,"; out="$out\"$esc\""; first=0; done
  printf '%s]' "$out"
}

[ "$(uname -m)" = "x86_64" ] && pass architecture-x86_64 || fail architecture-x86_64
[ -r /etc/openwrt_release ] || fail openwrt-release-missing
. /etc/openwrt_release 2>/dev/null || true
case "${DISTRIB_RELEASE:-}" in 25.12.*) pass openwrt-25.12-series;; *) fail openwrt-25.12-series;; esac
have ubus || fail ubus-missing
have jsonfilter || fail jsonfilter-missing
[ -x /usr/sbin/performance-manager.uc ] && pass core-installed || fail core-installed
luci_present=false
[ -r /usr/share/luci/menu.d/luci-app-performance-manager.json ] && luci_present=true
rill_present=false
[ -x /etc/init.d/performance-manager-rill ] && rill_present=true
if [ "$luci_present" = false ]; then pass core-with-luci-absent; elif [ "$REQUIRE_CORE_ONLY" = 1 ]; then fail core-with-luci-absent; fi
if [ "$rill_present" = false ]; then pass core-with-rill-absent; elif [ "$REQUIRE_CORE_ONLY" = 1 ]; then fail core-with-rill-absent; fi

start_ms=$(awk '{printf "%d", $1*1000}' /proc/uptime)
/etc/init.d/performance-manager restart >/dev/null 2>&1 || fail core-restart
ready=0; i=0
while [ "$i" -lt 50 ]; do
  if ubus -S list performance-manager >/dev/null 2>&1; then ready=1; break; fi
  sleep 0.1; i=$((i+1))
done
end_ms=$(awk '{printf "%d", $1*1000}' /proc/uptime)
boot_ms=$((end_ms-start_ms))
[ "$ready" -eq 1 ] && pass core-ubus-ready || fail core-ubus-ready

STATUS=$(ubus call performance-manager status '{}' 2>/dev/null || printf '{}')
[ "$(jget "$STATUS" '@.running')" = "true" ] && pass core-running || fail core-running
ANALYZE=$(ubus call performance-manager analyze '{}' 2>/dev/null || printf '{}')
[ -n "$(jget "$ANALYZE" '@.confidence')" ] && pass analyzer-contract || fail analyzer-contract
TOPO=$(ubus call performance-manager topology '{}' 2>/dev/null || printf '{}')
[ -n "$(jget "$TOPO" '@.paths[0].routeIdentity')" ] && pass topology-route-identity || fail topology-route-identity
CAP=$(ubus call performance-manager capabilities '{}' 2>/dev/null || printf '{}')
printf '%s\n' "$CAP" | grep -q 'network.packet_steering.native' && pass native-packet-steering-observed || fail native-packet-steering-observed

# Rill is optional. If installed, prove Core remains live while Rill is stopped,
# then restore it and validate the effective directory access-control boundary.
# Upstream Rill v1.2.0 does not promise a magic socket inode mode.
rill_tested=false
if [ "$rill_present" = true ]; then
  rill_tested=true
  /etc/init.d/performance-manager-rill stop >/dev/null 2>&1 || true
  ubus call performance-manager status '{}' >/dev/null 2>&1 && pass core-with-rill-stopped || fail core-with-rill-stopped
  /etc/init.d/performance-manager-rill start >/dev/null 2>&1 || fail rill-start
  sleep 1
  [ -S /run/performance-manager/rill.sock ] && pass rill-socket || fail rill-socket
  dir_mode=$(stat -c '%a' /run/performance-manager 2>/dev/null || busybox stat -c '%a' /run/performance-manager 2>/dev/null || true)
  dir_owner=$(stat -c '%U:%G' /run/performance-manager 2>/dev/null || busybox stat -c '%U:%G' /run/performance-manager 2>/dev/null || true)
  sock_owner=$(stat -c '%U:%G' /run/performance-manager/rill.sock 2>/dev/null || busybox stat -c '%U:%G' /run/performance-manager/rill.sock 2>/dev/null || true)
  [ "$dir_mode" = "750" ] && pass rill-socket-directory-mode-0750 || fail rill-socket-directory-mode-0750
  [ "$dir_owner" = "performance-manager-rill:performance-manager-rill" ] && pass rill-socket-directory-owner || fail rill-socket-directory-owner
  [ "$sock_owner" = "performance-manager-rill:performance-manager-rill" ] && pass rill-socket-service-owner || fail rill-socket-service-owner
  rpid=$(pidof rill-pm-adapter 2>/dev/null | awk '{print $1}')
  service_uid=$(id -u performance-manager-rill 2>/dev/null || true)
  process_uid=$([ -n "$rpid" ] && awk '/^Uid:/ {print $2}' "/proc/$rpid/status" 2>/dev/null || true)
  [ -n "$service_uid" ] && [ "$process_uid" = "$service_uid" ] && pass rill-listens-as-dedicated-service-user || fail rill-listens-as-dedicated-service-user
  if id nobody >/dev/null 2>&1; then
    if su nobody -s /bin/sh -c 'test -x /run/performance-manager' >/dev/null 2>&1; then
      fail rill-socket-unauthorized-no-traverse
    else
      pass rill-socket-unauthorized-no-traverse
    fi
  else
    fail rill-socket-unauthorized-user-unavailable
  fi
  RS=$(ubus call performance-manager rill_status '{}' 2>/dev/null || printf '{}')
  rstate=$(jget "$RS" '@.state')
  case "$rstate" in available|learning) pass rill-root-core-connect;; *) fail rill-root-core-connect;; esac
  [ "$(jget "$RS" '@.mode')" = "shadow" ] && pass rill-shadow || fail rill-shadow
  effective_binary=$(jget "$RS" '@.binary.effective')
  if [ -n "$effective_binary" ] && [ -r "$effective_binary" ]; then
    adapter_sha=$(sha256sum "$effective_binary" | awk '{print $1}')
    [ -n "$adapter_sha" ] && pass rill-adapter-sha-captured || fail rill-adapter-sha-captured
  else
    fail rill-adapter-sha-captured
  fi
fi

mutation_tested=false
mutation_ok=null
if [ "$ALLOW_MUTATION" = "1" ]; then
  mutation_tested=true
  REC=$(ubus call performance-manager recommendations '{}' 2>/dev/null || printf '{}')
  aid=$(jget "$REC" '@.actions[0].id')
  target=$(jget "$REC" '@.actions[0].applyTarget')
  if [ "$aid" = "nic.ring.floor" ] && [ -n "$target" ]; then
    ps_before=$(uci -q get network.@globals[0].packet_steering 2>/dev/null || true)
    APPLY=$(ubus call performance-manager apply "{\"actionId\":\"$aid\",\"target\":\"$target\"}" 2>/dev/null || printf '{}')
    txid=$(jget "$APPLY" '@.transaction.transactionId')
    if [ "$(jget "$APPLY" '@.ok')" = "true" ] && [ -n "$txid" ]; then
      RB=$(ubus call performance-manager rollback "{\"transactionId\":\"$txid\"}" 2>/dev/null || printf '{}')
      if [ "$(jget "$RB" '@.ok')" = "true" ]; then pass ring-apply-manual-rollback; else fail ring-apply-manual-rollback; fi
      APPLY2=$(ubus call performance-manager apply "{\"actionId\":\"$aid\",\"target\":\"$target\"}" 2>/dev/null || printf '{}')
      if [ "$(jget "$APPLY2" '@.ok')" = "true" ]; then
        CL=$(ubus call performance-manager cleanup '{"reason":"target-gate"}' 2>/dev/null || printf '{}')
        if [ "$(jget "$CL" '@.ok')" = "true" ]; then pass ownership-cleanup; mutation_ok=true; else fail ownership-cleanup; mutation_ok=false; fi
      else fail second-ring-apply-for-cleanup; mutation_ok=false; fi
      ps_after=$(uci -q get network.@globals[0].packet_steering 2>/dev/null || true)
      [ "$ps_before" = "$ps_after" ] && pass native-packet-steering-not-seized || fail native-packet-steering-not-seized
    else
      fail legal-ring-candidate-apply
      mutation_ok=false
    fi
  else
    fail legal-conservative-ring-candidate
    mutation_ok=false
  fi
fi

LOCKS=$(ubus call performance-manager locks '{}' 2>/dev/null || printf '{}')
lock_count=$(printf '%s\n' "$LOCKS" | jsonfilter -e '@.locks[*].resource' 2>/dev/null | wc -l | tr -d ' ')
[ "${lock_count:-0}" = "0" ] && pass no-stale-locks || fail no-stale-locks

pass_json=$(json_array "$passes")
fail_json=$(json_array "$failures")
release="${DISTRIB_RELEASE:-unknown}"
adapter_json=null
[ -n "$adapter_sha" ] && adapter_json="\"$adapter_sha\""
cat >"$OUT" <<EOF_JSON
{
  "schemaVersion": 2,
  "gate": "openwrt-target-runtime",
  "profile": "$TARGET_PROFILE",
  "pmCommitSha": "$PM_COMMIT_SHA",
  "adapterSha256": $adapter_json,
  "openwrtRelease": "$release",
  "architecture": "$(uname -m)",
  "coreStartMilliseconds": $boot_ms,
  "luciPresent": $luci_present,
  "rillPresent": $rill_present,
  "coreOnlyRequired": $([ "$REQUIRE_CORE_ONLY" = 1 ] && printf true || printf false),
  "rillTested": $rill_tested,
  "mutationOptIn": $mutation_tested,
  "mutationPassed": $mutation_ok,
  "passes": $pass_json,
  "failures": $fail_json,
  "verdict": "$([ -z "$failures" ] && printf PASS || printf FAIL)",
  "passed": $([ -z "$failures" ] && printf true || printf false)
}
EOF_JSON
printf 'Evidence: %s\n' "$OUT"
[ -z "$failures" ]
