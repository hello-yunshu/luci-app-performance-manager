#!/bin/sh
set -eu
fail(){ echo "FAIL: $*" >&2; exit 1; }
pass(){ echo "PASS: $*"; }
[ -x /usr/sbin/performance-manager.uc ] || fail 'core executable missing'
/etc/init.d/performance-manager enabled || fail 'core not enabled'
/etc/init.d/performance-manager restart
sleep 2
ubus -S list performance-manager >/dev/null || fail 'ubus object missing'
STATUS="$(ubus call performance-manager status '{}')"; echo "$STATUS" | grep -q '"running": true' || fail 'core status not running'; pass 'core standalone + ubus'
CAP="$(ubus call performance-manager capabilities '{}')"; echo "$CAP" | grep -q 'network.packet_steering.native' || fail 'native packet steering capability absent'; pass 'native Packet Steering provider observed'
REC="$(ubus call performance-manager recommendations '{}')"; echo "$REC" | grep -q 'actions' || fail 'recommendations malformed'; pass 'recommendation contract'
ubus call performance-manager transactions '{}' >/dev/null; ubus call performance-manager locks '{}' >/dev/null; pass 'transactions + locks API'
if [ -x /etc/init.d/performance-manager-rill ]; then
  /etc/init.d/performance-manager-rill restart; sleep 1
  [ -S /run/performance-manager/rill.sock ] || fail 'Rill socket missing'
  MODE="$(stat -c '%a' /run/performance-manager 2>/dev/null || busybox stat -c '%a' /run/performance-manager)"
  [ "$MODE" = 750 ] || fail "Rill socket directory mode $MODE != 750"
  OWNER="$(stat -c '%U:%G' /run/performance-manager 2>/dev/null || busybox stat -c '%U:%G' /run/performance-manager)"
  [ "$OWNER" = performance-manager-rill:performance-manager-rill ] || fail "Rill socket directory owner $OWNER"
  ubus call performance-manager rill_status '{}' | grep -q 'Shadow' || fail 'Rill not Shadow'
  pass 'Rill UDS directory access control + Shadow status'
fi
# Safety: smoke test never applies an action and never starts active traffic.
pass 'no silent actuation / no active benchmark in smoke test'
