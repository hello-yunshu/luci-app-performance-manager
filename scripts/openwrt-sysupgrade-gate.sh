#!/bin/sh
# Two-stage sysupgrade evidence gate for OpenWrt Performance Manager.
# Usage on the SAME test VM:
#   ./openwrt-sysupgrade-gate.sh prepare
#   <perform the intended OpenWrt sysupgrade and reboot>
#   ./openwrt-sysupgrade-gate.sh verify
# The prepare marker lives only inside paths explicitly covered by the package
# keep.d rules. verify requires a changed boot_id, so running both stages in the
# same boot cannot produce passing release evidence.
set -eu

MODE="${1:-}"
ROOT=/etc/performance-manager
PRE="$ROOT/.sysupgrade-gate-pre"
CORE_SENTINEL="$ROOT/.sysupgrade-gate-core-sentinel"
RILL_DIR="$ROOT/rill"
RILL_SENTINEL="$RILL_DIR/.sysupgrade-gate-rill-sentinel"
OUT="${PM_EVIDENCE_OUT:-/tmp/performance-manager-sysupgrade-gate.json}"

boot_id() { cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unknown; }
sha_file() { sha256sum "$1" | awk '{print $1}'; }
policy_count() { find "$ROOT/policies" -type f -name '*.json' 2>/dev/null | wc -l | tr -d ' '; }
policy_sha() { find "$ROOT/policies" -type f -name '*.json' -exec sha256sum {} + 2>/dev/null | sort | sha256sum | awk '{print $1}'; }
package_sha() {
  if [ -n "${PM_INSTALLED_PACKAGE_SHA256:-}" ]; then
    printf '%s' "$PM_INSTALLED_PACKAGE_SHA256"
  elif [ -n "${PM_PACKAGE_IDENTITY_PATH:-}" ] && [ -r "$PM_PACKAGE_IDENTITY_PATH" ]; then
    sha_file "$PM_PACKAGE_IDENTITY_PATH"
  else
    sha_file /etc/config/performance-manager
  fi
}
json_array() {
  oldifs="$IFS"; IFS=','; set -- $1; IFS="$oldifs"
  out='['; first=1
  for v in "$@"; do [ -n "$v" ] || continue; esc=$(printf '%s' "$v" | sed 's/\\/\\\\/g;s/"/\\"/g'); [ "$first" -eq 1 ] || out="$out,"; out="$out\"$esc\""; first=0; done
  printf '%s]' "$out"
}

case "$MODE" in
prepare)
  [ -r /etc/config/performance-manager ] || { echo 'performance-manager config missing' >&2; exit 1; }
  mkdir -p "$ROOT"
  b="$(boot_id)"
  csha="$(sha_file /etc/config/performance-manager)"
  psha="$(policy_sha)"
  pkgsha="$(package_sha)"
  printf 'opm-sysupgrade-gate:%s\n' "$b" > "$CORE_SENTINEL"
  rill_required=0
  if [ -x /etc/init.d/performance-manager-rill ]; then
    rill_required=1
    mkdir -p "$RILL_DIR"
    printf 'opm-rill-sysupgrade-gate:%s\n' "$b" > "$RILL_SENTINEL"
  fi
  cat > "$PRE" <<EOF_PRE
boot_id=$b
config_sha256=$csha
policy_sha256=$psha
package_sha256=$pkgsha
rill_required=$rill_required
EOF_PRE
  sync
  echo "Prepared sysupgrade evidence on boot $b. Perform the intended sysupgrade/reboot, then run: $0 verify"
  ;;
verify)
  [ -r "$PRE" ] || { echo 'prepare evidence missing after sysupgrade' >&2; exit 1; }
  # shellcheck disable=SC1090
  . "$PRE"
  passes=''; failures=''
  pass() { passes="${passes}${passes:+,}$1"; printf 'PASS: %s\n' "$1"; }
  fail() { failures="${failures}${failures:+,}$1"; printf 'FAIL: %s\n' "$1" >&2; }
  now_boot="$(boot_id)"
  [ "$now_boot" != "$boot_id" ] && pass boot-changed || fail boot-changed
  [ -r "$CORE_SENTINEL" ] && pass core-persistent-root-survived || fail core-persistent-root-survived
  if [ -r /etc/config/performance-manager ] && [ "$(sha_file /etc/config/performance-manager)" = "$config_sha256" ]; then pass config-preserved; else fail config-preserved; fi
  now_psha="$(policy_sha)"
  [ "$now_psha" = "$policy_sha256" ] && pass policy-preserved || fail policy-preserved
  if [ "${rill_required:-0}" = 1 ]; then
    [ -r "$RILL_SENTINEL" ] && pass rill-persistent-root-survived || fail rill-persistent-root-survived
  fi
  if command -v ubus >/dev/null 2>&1 && ubus -S list performance-manager >/dev/null 2>&1; then pass core-running-after-upgrade; else fail core-running-after-upgrade; fi
  locks=0
  if command -v ubus >/dev/null 2>&1 && command -v jsonfilter >/dev/null 2>&1; then
    L="$(ubus call performance-manager locks '{}' 2>/dev/null || printf '{}')"
    locks=$(printf '%s\n' "$L" | jsonfilter -e '@.locks[*].resource' 2>/dev/null | wc -l | tr -d ' ')
  fi
  [ "${locks:-0}" = 0 ] && pass no-stale-locks-after-upgrade || fail no-stale-locks-after-upgrade
  pending=$(find "$ROOT/pending" -type f 2>/dev/null | wc -l | tr -d ' '); pending=${pending:-0}
  [ "$pending" = 0 ] && pass no-stale-pending-marker || fail no-stale-pending-marker
  now_pkgsha="$(package_sha)"
  adapter_sha="${PM_ADAPTER_SHA256:-unknown}"
  cat > "$OUT" <<EOF_JSON
{
  "rawFacts": {
    "installedPackages": {"luci-app-performance-manager-all": {"apkSha256": "$now_pkgsha", "version": "${PM_INSTALLED_PACKAGE_VERSION:-unknown}", "installedPayload": {}}},
    "upgrade": {
      "before": {"bootId": "$boot_id", "packageSha256": "$package_sha256", "configSha256": "$config_sha256", "policySha256": "$policy_sha256"},
      "after": {"bootId": "$now_boot", "packageSha256": "$now_pkgsha", "configSha256": "$(sha_file /etc/config/performance-manager)", "policySha256": "$now_psha", "adapterSha256": "$adapter_sha", "pendingMutationCount": $pending, "coreStarted": $([ -z "$failures" ] && printf true || printf false), "staleLocks": $locks}
    }
  }
}
EOF_JSON
  rm -f "$PRE" "$CORE_SENTINEL" "$RILL_SENTINEL"
  printf 'Evidence: %s\n' "$OUT"
  [ -z "$failures" ]
  ;;
*)
  echo "usage: $0 prepare|verify" >&2
  exit 2
  ;;
esac
