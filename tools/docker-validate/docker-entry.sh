#!/bin/sh
# Entry point: copy PM sources from mounted volume, compile-check Core, then hand
# over to procd (/sbin/init) as PID1 so the performance-manager service auto-starts.
# Run with --privileged (procd needs /dev, netlink, etc.).
set -eu
echo "=== [pm-gate] container boot (OpenWrt 25.12.5 x86/64) ==="
uname -m
cat /etc/openwrt_release

SRC=/home/pm-src
if [ -d "$SRC/package/performance-manager" ]; then
  echo "=== [pm-gate] installing Core files into container rootfs ==="
  mkdir -p \
    /etc/config /etc/init.d /etc/uci-defaults \
    /usr/sbin /usr/share/performance-manager/profiles /usr/share/performance-manager/schemas \
    /lib/upgrade/keep.d
  cp "$SRC/package/performance-manager/files/etc/init.d/performance-manager" /etc/init.d/performance-manager
  cp "$SRC/package/performance-manager/files/etc/config/performance-manager" /etc/config/performance-manager
  cp "$SRC/package/performance-manager/files/etc/uci-defaults/90-performance-manager" /etc/uci-defaults/90-performance-manager
  # Install the RAW shipped Core verbatim.  The production source is written
  # callee-before-caller (ucode resolves free-variable bindings at function
  # DEFINITION time and does not hoist function declarations), so it runs as a
  # daemon without any transform.  There is deliberately NO convert_hoist step
  # (CORE BLOCKER C): what is tested == what is shipped == what the APK installs.
  cp "$SRC/package/performance-manager/files/usr/sbin/performance-manager.uc" /usr/sbin/performance-manager.uc
  cp "$SRC/package/performance-manager/files/usr/share/performance-manager/contracts.uc" /usr/share/performance-manager/contracts.uc
  cp -a "$SRC/package/performance-manager/files/usr/share/performance-manager/profiles/." /usr/share/performance-manager/profiles/
  cp -a "$SRC/contracts/"*.schema.json /usr/share/performance-manager/schemas/
  cp "$SRC/package/performance-manager/files/lib/upgrade/keep.d/performance-manager" /lib/upgrade/keep.d/performance-manager
  chmod +x /etc/init.d/performance-manager /usr/sbin/performance-manager.uc /etc/uci-defaults/90-performance-manager
else
  echo "=== [pm-gate] WARNING: /home/pm-src not mounted; expecting pre-baked files ==="
fi

echo "=== [pm-gate] Core ucode compile check (equival to CI openwrt-ucode) ==="
/usr/bin/ucode -c -o /tmp/performance-manager.ucb /usr/sbin/performance-manager.uc && echo "COMPILE-OK"

echo "=== [pm-gate] handing over to procd (/sbin/init) as PID1 ==="
exec /sbin/init
