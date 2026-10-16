#!/usr/bin/env bash
# Isolated, official OpenWrt userspace for loading qualified package bytes.
set -euo pipefail
version=${1:?OpenWrt version required}
output=${2:?new output directory required}
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]
test ! -e "$output"
mkdir -p "$output/rootfs"
output=$(realpath "$output")
base="https://downloads.openwrt.org/releases/$version/targets/x86/64"
archive="openwrt-$version-x86-64-rootfs.tar.gz"
curl --fail --silent --show-error --location --retry 3 "$base/sha256sums" -o "$output/sha256sums"
mapfile -t digests < <(awk -v file="*$archive" '$2 == file {print $1}' "$output/sha256sums")
test "${#digests[@]}" -eq 1
[[ "${digests[0]}" =~ ^[a-f0-9]{64}$ ]]
curl --fail --silent --show-error --location --retry 3 "$base/$archive" -o "$output/$archive"
printf '%s *%s\n' "${digests[0]}" "$output/$archive" | sha256sum -c -
tar --no-same-owner -xzf "$output/$archive" -C "$output/rootfs"
loader="$output/rootfs/lib/ld-musl-x86_64.so.1"
test -f "$loader"
cat > "$output/apk-inspector" <<EOF
#!/bin/sh
exec "$loader" --library-path "$output/rootfs/lib:$output/rootfs/usr/lib" "$output/rootfs/usr/bin/apk" "\$@"
EOF
chmod 755 "$output/apk-inspector"
"$output/apk-inspector" --version
