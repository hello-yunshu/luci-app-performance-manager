#!/usr/bin/env bash
set -euo pipefail

CONTAINER="${1:-pm-ui-gate}"
PORT="${2:-18080}"
RILL_MANAGER_PACKAGE="${3:-${PM_RILL_MANAGER_DIR:-}}"
LANG_CODE="${PM_UI_LANG:-en}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI="$ROOT/package/luci-app-performance-manager"
CORE="$ROOT/package/performance-manager/files"

command -v docker >/dev/null || { echo 'missing host command: docker' >&2; exit 1; }
command -v jq >/dev/null || { echo 'missing host command: jq' >&2; exit 1; }
docker exec "$CONTAINER" sh -c 'set -eu; for command in bash jq curl ucode ubus; do command -v "$command" >/dev/null; done'
test -n "$RILL_MANAGER_PACKAGE" || { echo 'missing exact Rill Runtime Manager package directory' >&2; exit 1; }
test -f "$RILL_MANAGER_PACKAGE/files/usr/libexec/rpcd/rill-runtime-manager"
test -f "$RILL_MANAGER_PACKAGE/files/usr/libexec/rill-runtime-manager"
test -f "$RILL_MANAGER_PACKAGE/files/usr/share/rpcd/acl.d/rill-runtime-manager.json"
test -f "$RILL_MANAGER_PACKAGE/files/usr/share/rill-runtime-manager/consumer-compatibility.schema.json"

docker exec "$CONTAINER" mkdir -p /usr/libexec/rpcd /usr/share/luci/menu.d /usr/share/rpcd/acl.d \
	/usr/lib/lua/luci/i18n /usr/share/performance-manager /usr/share/rill-runtime-manager \
	/www/luci-static/resources/performance-manager /www/luci-static/resources/view/performance-manager

docker cp "$CORE/etc/config/performance-manager" "$CONTAINER:/etc/config/performance-manager"
docker cp "$CORE/etc/init.d/performance-manager" "$CONTAINER:/etc/init.d/performance-manager"
docker cp "$CORE/etc/uci-defaults/90-performance-manager" "$CONTAINER:/etc/uci-defaults/90-performance-manager"
docker cp "$CORE/usr/sbin/performance-manager.uc" "$CONTAINER:/usr/sbin/performance-manager.uc"
docker cp "$CORE/usr/share/performance-manager/." "$CONTAINER:/usr/share/performance-manager/"
docker cp "$UI/root/usr/share/luci/menu.d/luci-app-performance-manager.json" "$CONTAINER:/usr/share/luci/menu.d/"
docker cp "$UI/root/usr/share/rpcd/acl.d/luci-app-performance-manager.json" "$CONTAINER:/usr/share/rpcd/acl.d/"
docker cp "$RILL_MANAGER_PACKAGE/files/usr/libexec/rpcd/rill-runtime-manager" "$CONTAINER:/usr/libexec/rpcd/"
docker cp "$RILL_MANAGER_PACKAGE/files/usr/libexec/rill-runtime-manager" "$CONTAINER:/usr/libexec/"
docker cp "$RILL_MANAGER_PACKAGE/files/usr/share/rpcd/acl.d/rill-runtime-manager.json" "$CONTAINER:/usr/share/rpcd/acl.d/"
docker cp "$RILL_MANAGER_PACKAGE/files/usr/share/rill-runtime-manager/consumer-compatibility.schema.json" "$CONTAINER:/usr/share/rill-runtime-manager/"
docker cp "$UI/htdocs/luci-static/resources/performance-manager/." "$CONTAINER:/www/luci-static/resources/performance-manager/"
docker cp "$UI/htdocs/luci-static/resources/view/performance-manager/." "$CONTAINER:/www/luci-static/resources/view/performance-manager/"

if [ -n "${PM_UI_LMO:-}" ]; then
	docker cp "$PM_UI_LMO" "$CONTAINER:/usr/lib/lua/luci/i18n/performance-manager.zh-cn.lmo"
fi

PKG_VERSION="$(cat "$ROOT/VERSION")"
PKG_RELEASE="$(sed -n 's/^PKG_RELEASE:=//p' "$UI/Makefile" | head -n1)"
PKG_FULL_VERSION="$PKG_VERSION-r$PKG_RELEASE"
docker exec "$CONTAINER" sh -c "
	set -eu
	chmod +x /etc/init.d/performance-manager /etc/uci-defaults/90-performance-manager /usr/sbin/performance-manager.uc
	chmod +x /usr/libexec/rpcd/rill-runtime-manager /usr/libexec/rill-runtime-manager
	sed -i 's|@PKG_VERSION@|$PKG_VERSION|g; s|@PKG_RELEASE@|$PKG_RELEASE|g; s|@PKG_FULL_VERSION@|$PKG_FULL_VERSION|g' \
		/www/luci-static/resources/performance-manager/ui.js
	uci set uhttpd.main.listen_http='0.0.0.0:$PORT'
	uci set uhttpd.main.listen_https=''
	uci set luci.main.mediaurlbase='/luci-static/bootstrap'
	uci set luci.main.lang='$LANG_CODE'
	uci commit uhttpd
	uci commit luci
	/etc/uci-defaults/90-performance-manager
	rm -rf /tmp/luci-indexcache* /tmp/luci-modulecache*
	/etc/init.d/rpcd restart >/dev/null 2>&1
	/etc/init.d/uhttpd restart >/dev/null 2>&1
"

HASH="$(docker exec "$CONTAINER" openssl passwd -6 -salt pm-ui-gate "${PM_UI_PASSWORD:-pm-gate}")"
docker exec "$CONTAINER" sh -c "sed -i 's|^root:[^:]*:|root:$HASH:|' /etc/shadow"

for _ in $(seq 1 10); do
	status="$(curl -sS --max-time 3 -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/cgi-bin/luci/" 2>/dev/null || true)"
	if [ "$status" = 200 ] || [ "$status" = 302 ] || [ "$status" = 403 ]; then
		echo "provisioned $CONTAINER on 127.0.0.1:$PORT lang=$LANG_CODE"
		break
	fi
	sleep 1
done

manager_status_json=''
for _ in $(seq 1 10); do
	manager_status_json="$(docker exec "$CONTAINER" ubus call rill-runtime-manager status '{}' 2>/dev/null || true)"
	if [ -n "$manager_status_json" ]; then
		break
	fi
	sleep 1
done
if [ -z "$manager_status_json" ]; then
	echo 'rill-runtime-manager status RPC is unavailable' >&2
	docker exec "$CONTAINER" logread -e rpcd 2>/dev/null | tail -40 >&2 || true
	exit 1
fi
printf '%s\n' "$manager_status_json" | jq -e '.ok == true and .installed == false and .channel == "none"' >/dev/null || {
	echo 'Rill Manager status did not report a healthy, Runtime-not-installed state' >&2
	printf '%s\n' "$manager_status_json" >&2
	exit 1
}
echo 'rill-runtime-manager status RPC is available with no Runtime installed'

status_json=''
status_json="$(docker exec "$CONTAINER" ubus call performance-manager status '{}' 2>/dev/null || true)"
if [ -z "$status_json" ]; then
	# Some rootfs Docker hosts intentionally deny procd's cgroup/jail setup.
	# Keep the same production daemon and ubus API, but launch it directly in
	# this disposable test container when its init action cannot spawn it.
	docker exec -d "$CONTAINER" ucode /usr/sbin/performance-manager.uc
fi
for _ in $(seq 1 10); do
	status_json="$(docker exec "$CONTAINER" ubus call performance-manager status '{}' 2>/dev/null || true)"
	if [ -n "$status_json" ]; then
		printf '%s\n' "$status_json"
		echo 'performance-manager ubus status is available'
		exit 0
	fi
	sleep 1
done
echo 'performance-manager ubus status is unavailable' >&2
docker exec "$CONTAINER" logread -e performance-manager 2>/dev/null | tail -40 >&2 || true
exit 1
