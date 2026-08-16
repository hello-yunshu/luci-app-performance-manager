#!/bin/sh
# Run openwrt-target-gate.sh inside the Docker container
set -e

echo "=== Starting openwrt-25.12.5 docker container ==="
echo "=== Copying performance-manager sources to /tmp/pm-src ==="
mkdir -p /tmp/pm-src/package/performance-manager/files
cp -a /home/pm-src/package/performance-manager/files/. /tmp/pm-src/package/performance-manager/files/
cp -a /home/pm-src/profiles /tmp/pm-src/
cp -a /home/pm-src/scripts/openwrt-target-gate.sh /tmp/pm-src/

echo "=== Installing target-gate dependencies ==="
# jsonfilter + ubus ship in the base image; jq is optional (gate script uses
# jsonfilter). Container may be offline (netifd bridged eth0 into br-lan and
# dropped the docker default route), so never fail the gate on apk.
apk add --no-cache jq >/dev/null 2>&1 || echo "warn: apk offline; continuing with base packages"

# Fractional-capable sleep shim: container busybox lacks FEATURE_FLOAT_SLEEP
# while real OpenWrt 25.12.x supports it. /usr/bin precedes /bin in PATH, so
# this intercepts the gate's `sleep 0.1` and delegates to the real busybox.
cp /home/pm-src/tools/docker-validate/sleep-shim /usr/bin/sleep
chmod +x /usr/bin/sleep

echo "=== Installing performance-manager core files ==="
mkdir -p \
  /etc/config \
  /etc/init.d \
  /etc/uci-defaults \
  /usr/sbin \
  /usr/share/performance-manager \
  /lib/upgrade/keep.d

cp /tmp/pm-src/package/performance-manager/files/etc/init.d/performance-manager /etc/init.d/
chmod +x /etc/init.d/performance-manager
cp /tmp/pm-src/package/performance-manager/files/etc/config/performance-manager /etc/config/
cp /tmp/pm-src/package/performance-manager/files/etc/uci-defaults/90-performance-manager /etc/uci-defaults/
chmod +x /etc/uci-defaults/90-performance-manager
# Install the RAW shipped Core verbatim.  The production source is written
# callee-before-caller (ucode resolves free-variable bindings at function
# DEFINITION time and does not hoist function declarations), so it runs as a
# daemon without any transform.  There is deliberately NO convert_hoist step
# (CORE BLOCKER C): what is tested == what is shipped == what the APK installs.
cp /tmp/pm-src/package/performance-manager/files/usr/sbin/performance-manager.uc /usr/sbin/
chmod +x /usr/sbin/performance-manager.uc
cp /tmp/pm-src/package/performance-manager/files/usr/share/performance-manager/contracts.uc /usr/share/performance-manager/
mkdir -p /usr/share/performance-manager/profiles
cp -a /tmp/pm-src/package/performance-manager/files/usr/share/performance-manager/profiles/* /usr/share/performance-manager/profiles/
mkdir -p /usr/share/performance-manager/schemas
cp -a /home/pm-src/contracts/*.schema.json /usr/share/performance-manager/schemas/
cp /tmp/pm-src/package/performance-manager/files/lib/upgrade/keep.d/performance-manager /lib/upgrade/keep.d/

echo "=== Core files installed. Compiling ucode to bytecode ==="
/usr/bin/ucode -c -o /tmp/performance-manager.ucb /usr/sbin/performance-manager.uc
echo "✓ Compilation OK"

echo "=== Running openwrt-target-gate.sh (CORE-ONLY mode) ==="
chmod +x /tmp/pm-src/openwrt-target-gate.sh
export PM_REQUIRE_CORE_ONLY=1
export PM_EVIDENCE_OUT=/tmp/performance-manager-target-gate.json
/tmp/pm-src/openwrt-target-gate.sh

echo "=== Done. Evidence at $PM_EVIDENCE_OUT ==="
cat "$PM_EVIDENCE_OUT"
