#!/bin/sh
# Host-side build of the runtime-correct (ucode-hoisted) Core artifact.
#
# Why this exists: ucode does not hoist top-level `function` declarations and
# resolves free variables when a function is DEFINED, so any forward reference
# in the readable source crashes at runtime (the Docker target gate caught this
# on real OpenWrt 25.12.5). convert_hoist.py rewrites every top-level function
# into a hoisted `let name;` binding + `name = (params) => { ... };` assignment,
# which makes all cross-function calls resolve.
#
# The readable source stays in package/performance-manager/files/... (the Python
# unittest suite slices function bodies by `function name(` markers, so it must
# keep declaration syntax). This helper emits the converted artifact under
# tools/docker-validate/build/ for the container gate to install.
#
# Usage: sh tools/docker-validate/build-core.sh [OUT]
set -eu
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SRC="$ROOT/package/performance-manager/files/usr/sbin/performance-manager.uc"
OUT="${1:-$ROOT/tools/docker-validate/build/performance-manager.uc}"
mkdir -p "$(dirname "$OUT")"
python3 "$ROOT/tools/docker-validate/convert_hoist.py" "$SRC" "$OUT"
echo "converted Core artifact -> $OUT"
