#!/usr/bin/env bash
# Thin MacBook orchestration for repository-software portable validation.
set -u

ROOT=$(cd "$(dirname "$0")/../.." && pwd)
cd "$ROOT" || exit 1
ACTUAL_HEAD=$(git rev-parse HEAD 2>/dev/null || true)
EXPECTED_SHA=${PM_EXPECTED_SHA:-$ACTUAL_HEAD}
HOST_ARCH=$(uname -m)
DOCKER_PLATFORM=linux/amd64
EVIDENCE="$ROOT/local-evidence"
SOURCE="$EVIDENCE/source"
DOCKER="$EVIDENCE/docker"
PACKAGE="$EVIDENCE/package"
PORTABLE="$EVIDENCE/portable"
INPUT="$EVIDENCE/.artifact-input"
ARTIFACTS="$ROOT/local-artifacts/x86_64"
PY=${PM_VALIDATION_PYTHON:-$ROOT/.venv/bin/python3}

# Evidence and extracted files are run-specific. The downloaded rootfs itself
# is intentionally outside these directories and is retained as a digest-bound
# cache.
rm -rf "$EVIDENCE" "$ARTIFACTS"

mkdir -p "$SOURCE" "$DOCKER" "$PACKAGE" "$PORTABLE"
source_verdict=NOT_EVALUATED
core_verdict=NOT_EVALUATED
runtime_verdict=NOT_EVALUATED
package_verdict=NOT_EVALUATED
service_verdict=NOT_EVALUATED
ubus_verdict=NOT_EVALUATED
removal_verdict=NOT_EVALUATED
artifact_verdict=NOT_EVALUATED
portable_verdict=BLOCKED
portable_gate_verdict=NOT_EVALUATED
rootfs_sha=
reason=

run_logged() {
    local log="$1"
    shift
    "$@" >"$log" 2>&1
}

report() {
    local report_reason="$1"
    local report_python="$PY"
    if [ ! -x "$report_python" ]; then report_python=$(command -v python3); fi
    "$report_python" scripts/build_local_validation_report.py \
        --out "$PORTABLE/portable-macos-docker.json" --commit "$ACTUAL_HEAD" \
        --host-arch "$HOST_ARCH" --docker-version "${DOCKER_VERSION:-unavailable}" \
        --rootfs-sha "$rootfs_sha" --source "$source_verdict" --core "$core_verdict" \
        --runtime "$runtime_verdict" --package "$package_verdict" \
        --service "$service_verdict" --ubus "$ubus_verdict" --removal "$removal_verdict" \
        --portable "$portable_verdict" --artifact-identity "$artifact_verdict" \
        --reason "$report_reason"
}

if [ -z "$ACTUAL_HEAD" ] || ! printf '%s' "$ACTUAL_HEAD" | grep -Eq '^[0-9a-f]{40}$'; then
    source_verdict=FAIL
    portable_verdict=FAIL
    report "invalid current commit SHA" || true
    echo "FAIL: invalid current commit SHA"
    exit 1
fi
if [ -z "$EXPECTED_SHA" ] || ! printf '%s' "$EXPECTED_SHA" | grep -Eq '^[0-9a-f]{40}$'; then
    source_verdict=FAIL
    portable_verdict=FAIL
    report "invalid expected commit SHA" || true
    echo "FAIL: invalid expected commit SHA"
    exit 1
fi
if [ "$ACTUAL_HEAD" != "$EXPECTED_SHA" ]; then
    source_verdict=FAIL
    portable_verdict=FAIL
    report "HEAD mismatch: expected $EXPECTED_SHA, actual $ACTUAL_HEAD" || true
    echo "FAIL: HEAD mismatch"
    exit 1
fi
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
    source_verdict=FAIL
    portable_verdict=FAIL
    report "dirty-worktree"
    echo "FAIL: dirty-worktree"
    exit 1
fi

echo "[local-macos] validating commit $EXPECTED_SHA on macOS $HOST_ARCH"
if [ -n "${PM_VALIDATION_PYTHON:-}" ]; then
    if [ ! -x "$PY" ]; then source_verdict=FAIL; reason="configured validation Python is not executable"; fi
else
    if ! run_logged "$SOURCE/venv.log" python3 -m venv --system-site-packages .venv; then
        source_verdict=FAIL
        reason="source validation environment setup failed"
    else
        if ! run_logged "$SOURCE/dependencies.log" "$PY" -m pip install jsonschema pyyaml; then
            if "$PY" -c 'import jsonschema, yaml' >/dev/null 2>&1; then :
            elif python3 -c 'import jsonschema, yaml' >/dev/null 2>&1; then PY=$(command -v python3)
            else source_verdict=FAIL; reason="jsonschema/pyyaml are unavailable"; fi
        fi
    fi
fi
if [ "$source_verdict" = FAIL ]; then
    report "$reason"
    echo "FAIL: $reason"
    exit 1
fi
if [ "$source_verdict" != FAIL ]; then
    if run_logged "$SOURCE/unit-tests.log" "$PY" -m unittest discover -s tests -p 'test_*.py'; then unit=PASS; else unit=FAIL; fi
    if run_logged "$SOURCE/make-audit.log" env PATH="$(dirname "$PY"):$PATH" GITHUB_SHA="$EXPECTED_SHA" make audit; then audit=PASS; else audit=FAIL; fi
    "$PY" -c "import json,re; t=open('$SOURCE/unit-tests.log').read(); m=re.search(r'Ran (\d+) tests?',t); json.dump({'verdict':'$unit','testCount':int(m.group(1)) if m else None,'command':'python3 -m unittest discover -s tests -p test_*.py'},open('$SOURCE/test-report.json','w'),indent=2)"
    [ ! -f "$ROOT/docs/source-audit.json" ] || cp "$ROOT/docs/source-audit.json" "$SOURCE/source-audit.json"
    [ ! -f "$ROOT/docs/FINAL_AUDIT.json" ] || cp "$ROOT/docs/FINAL_AUDIT.json" "$SOURCE/FINAL_AUDIT.json"
    [ ! -f "$ROOT/docs/FINAL_AUDIT.md" ] || cp "$ROOT/docs/FINAL_AUDIT.md" "$SOURCE/FINAL_AUDIT.md"
    [ ! -f "$ROOT/docs/HOST_SYNTAX_REPORT.json" ] || cp "$ROOT/docs/HOST_SYNTAX_REPORT.json" "$SOURCE/host-syntax-report.json"
    [ ! -f "$ROOT/docs/RESOURCE_BUDGET.json" ] || cp "$ROOT/docs/RESOURCE_BUDGET.json" "$SOURCE/resource-budget.json"
    if [ "$unit" = PASS ] && [ "$audit" = PASS ]; then source_verdict=PASS; else source_verdict=FAIL; fi
fi

if [ "$source_verdict" != PASS ]; then
    portable_verdict=FAIL
    report "local source tests or make audit failed"
    echo "FAIL: local source closure"
    exit 1
fi

DOCKER_VERSION=$(docker version --format '{{.Server.Version}}' 2>&1 || true)
if ! command -v docker >/dev/null 2>&1; then reason=docker-unavailable
elif ! run_logged "$DOCKER/docker-version.log" docker version; then reason=docker-unavailable
elif ! run_logged "$DOCKER/docker-info.log" docker info; then reason=docker-unavailable
elif ! run_logged "$DOCKER/docker-amd64.log" docker run --rm --platform "$DOCKER_PLATFORM" alpine uname -m; then reason='linux/amd64 Docker emulation unavailable'
elif ! grep -qx x86_64 "$DOCKER/docker-amd64.log"; then reason='linux/amd64 Docker emulation returned a non-x86_64 guest'; fi

if [ -n "$reason" ]; then
    core_verdict=BLOCKED; runtime_verdict=BLOCKED; package_verdict=BLOCKED
    service_verdict=BLOCKED; ubus_verdict=BLOCKED; removal_verdict=BLOCKED
    report "$reason"
    echo "BLOCKED: $reason"
    exit 2
fi

ROOTFS_COMMAND='set -eu
export DEBIAN_FRONTEND=noninteractive
if ! apt-get update || ! apt-get install -y --no-install-recommends ca-certificates curl tar gzip; then
  echo BLOCKED: OpenWrt bootstrap dependencies unavailable
  exit 2
fi
rootfs=openwrt-25.12.5-x86-64-rootfs.tar.gz
base=https://downloads.openwrt.org/releases/25.12.5/targets/x86/64
if ! curl -fsSLo sha256sums "$base/sha256sums"; then
  echo BLOCKED: OpenWrt checksum source unavailable
  exit 2
fi
if [ ! -f "$rootfs" ]; then
  if ! curl -fsSLo "$rootfs" "$base/$rootfs"; then
    echo BLOCKED: OpenWrt rootfs source unavailable
    exit 2
  fi
fi
rootfs_sha=$(awk -v f="*$rootfs" '\''$2 == f {print $1}'\'' sha256sums)
if [ -z "$rootfs_sha" ]; then
  echo FAIL: OpenWrt rootfs is absent from sha256sums
  exit 1
fi
if ! printf "%s *%s\n" "$rootfs_sha" "$rootfs" | sha256sum -c -; then
  echo FAIL: OpenWrt rootfs checksum mismatch
  exit 1
fi
printf "{\n  \"url\": \"%s/%s\",\n  \"sha256\": \"%s\",\n  \"verified\": true\n}\n" "$base" "$rootfs" "$rootfs_sha" > local-evidence/docker/openwrt-rootfs-sha256.json
rm -rf .portable-rootfs
mkdir -p .portable-rootfs
tar -xzf "$rootfs" -C .portable-rootfs
rm -f .portable-rootfs/etc/resolv.conf
cp /etc/resolv.conf .portable-rootfs/etc/resolv.conf
if chroot .portable-rootfs /bin/sh -c "command -v apk >/dev/null 2>&1"; then
  chroot .portable-rootfs /bin/sh -c "apk update --no-check-certificate && apk add --no-check-certificate ucode ucode-mod-fs ucode-mod-ubus ucode-mod-uci ucode-mod-rtnl ucode-mod-uloop ucode-mod-socket ucode-mod-log coreutils-timeout"
else
  chroot .portable-rootfs /bin/sh -c "opkg update && opkg install ucode ucode-mod-fs ucode-mod-ubus ucode-mod-uci ucode-mod-rtnl ucode-mod-uloop ucode-mod-socket ucode-mod-log"
fi
chown -R "$PM_HOST_UID:$PM_HOST_GID" .portable-rootfs local-evidence/docker/openwrt-rootfs-sha256.json'

if ! run_logged "$DOCKER/rootfs-prepare.log" docker run --rm --platform "$DOCKER_PLATFORM" \
    -e PM_HOST_UID="$(id -u)" -e PM_HOST_GID="$(id -g)" \
    -v "$ROOT:/workspace" -w /workspace ubuntu:24.04 bash -lc "$ROOTFS_COMMAND"; then
    if grep -q '^BLOCKED:' "$DOCKER/rootfs-prepare.log"; then
        reason='OpenWrt server/network unavailable'
        core_verdict=BLOCKED; runtime_verdict=BLOCKED; package_verdict=BLOCKED
    else
        reason='OpenWrt rootfs download, checksum, extraction, or ucode installation failed'
        core_verdict=FAIL; runtime_verdict=BLOCKED; package_verdict=BLOCKED
    fi
    service_verdict=BLOCKED; ubus_verdict=BLOCKED; removal_verdict=BLOCKED
    report "$reason"
    if grep -q '^BLOCKED:' "$DOCKER/rootfs-prepare.log"; then
        echo "BLOCKED: $reason"
        exit 2
    fi
    echo "FAIL: $reason"
    exit 1
fi

if ! rootfs_sha=$("$PY" -c 'import json,sys,re; value=json.load(open(sys.argv[1])).get("sha256"); assert re.fullmatch(r"[0-9a-f]{64}", value or ""); print(value)' "$DOCKER/openwrt-rootfs-sha256.json"); then
    reason='verified rootfs SHA evidence is missing or invalid'
    core_verdict=FAIL; portable_verdict=FAIL
    report "$reason"; echo "FAIL: $reason"; exit 1
fi

if ! run_logged "$DOCKER/docker-build.log" docker build --platform "$DOCKER_PLATFORM" \
    --file tools/docker-validate/Dockerfile.local --tag "pm-openwrt-portable:$EXPECTED_SHA" .; then
    reason='Dockerfile.local build failed'; core_verdict=FAIL; portable_verdict=FAIL
    report "$reason"; echo "FAIL: $reason"; exit 1
fi
if run_logged "$DOCKER/image-arch.log" docker run --rm --platform "$DOCKER_PLATFORM" \
    --entrypoint /bin/uname "pm-openwrt-portable:$EXPECTED_SHA" -m && grep -qx x86_64 "$DOCKER/image-arch.log"; then :; else
    reason='portable Docker image did not start'; core_verdict=FAIL; portable_verdict=FAIL
    report "$reason"; echo "FAIL: $reason"; exit 1
fi
if ! run_logged "$DOCKER/harness-build.log" "$PY" tools/docker-validate/harness/build-harness.py "$DOCKER/core_runtime_test.uc" || \
   ! run_logged "$DOCKER/core-runtime.log" docker run --rm --platform "$DOCKER_PLATFORM" \
       -v "$DOCKER/core_runtime_test.uc:/tmp/core_runtime_test.uc:ro" \
       --entrypoint /usr/bin/ucode "pm-openwrt-portable:$EXPECTED_SHA" /tmp/core_runtime_test.uc; then
    reason='OpenWrt ucode Core harness failed'; core_verdict=FAIL; portable_verdict=FAIL
    report "$reason"; echo "FAIL: $reason"; exit 1
fi
core_verdict=PASS
printf '\nPORTABLE_DOCKER_PASS\n' >> "$DOCKER/core-runtime.log"

build_run_id=${PM_BUILD_RUN_ID:-}
ci_run_id=${PM_CI_RUN_ID:-}
if ! command -v gh >/dev/null 2>&1; then reason='gh CLI unavailable for same-SHA artifacts'
else
    mkdir -p "$INPUT/build" "$INPUT/ci" "$ARTIFACTS"
    if [ -z "$build_run_id" ]; then
        build_run_id=$(gh run list --workflow build-openwrt.yml --commit "$EXPECTED_SHA" --limit 20 \
            --json databaseId,status,conclusion,headSha 2>"$EVIDENCE/gh-run-list-build.log" | \
            "$PY" -c 'import json,sys; rows=json.load(sys.stdin); print(next((r.get("databaseId","") for r in rows if r.get("headSha")==sys.argv[1] and r.get("status")=="completed" and r.get("conclusion")=="success"), ""))' "$EXPECTED_SHA")
    fi
    if [ -z "$ci_run_id" ]; then
        ci_run_id=$(gh run list --workflow ci.yml --commit "$EXPECTED_SHA" --limit 20 \
            --json databaseId,status,conclusion,headSha 2>"$EVIDENCE/gh-run-list-ci.log" | \
            "$PY" -c 'import json,sys; rows=json.load(sys.stdin); print(next((r.get("databaseId","") for r in rows if r.get("headSha")==sys.argv[1] and r.get("status")=="completed" and r.get("conclusion")=="success"), ""))' "$EXPECTED_SHA")
    fi
    if [ -z "$build_run_id" ] || [ -z "$ci_run_id" ]; then reason='same-SHA Build or CI artifact unavailable'
    elif ! run_logged "$EVIDENCE/verify-build-run.log" "$PY" scripts/verify_action_run_identity.py --run-id "$build_run_id" --expected-sha "$EXPECTED_SHA" --expected-workflow 'Build OpenWrt (remote SDK)' --expected-workflow-path '.github/workflows/build-openwrt.yml' || \
         ! run_logged "$EVIDENCE/verify-ci-run.log" "$PY" scripts/verify_action_run_identity.py --run-id "$ci_run_id" --expected-sha "$EXPECTED_SHA" --expected-workflow CI --expected-workflow-path '.github/workflows/ci.yml'; then
        reason='same-SHA workflow identity or terminal conclusion failed'
    elif ! run_logged "$EVIDENCE/download-build.log" gh run download "$build_run_id" --dir "$INPUT/build" || \
         ! run_logged "$EVIDENCE/download-ci.log" gh run download "$ci_run_id" --dir "$INPUT/ci"; then reason='same-SHA artifact download failed'
    else
        build_metadata=$(find "$INPUT/build" -type f -path '*x86-64-x86_64-packages-and-evidence/build-metadata.json' -print | sed -n '1p')
        if [ -z "$build_metadata" ]; then reason='x86_64 same-SHA Build artifact unavailable'
        else
            cp -a "$(dirname "$build_metadata")/." "$ARTIFACTS/"
            shasum -a 256 "$ARTIFACTS"/*.apk > "$ARTIFACTS/checksums" 2>"$EVIDENCE/checksums.log" || true
            if "$PY" - "$ARTIFACTS" "$EXPECTED_SHA" >"$EVIDENCE/artifact-identity.log" 2>&1 <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'scripts'))
from artifact_identity import resolve_artifact
root=Path(sys.argv[1]); expected=sys.argv[2]
build=json.loads((root/'build-metadata.json').read_text())
verify=json.loads((root/'docs/apk-verification.json').read_text())
if build.get('repositoryCommitSha') != expected: raise SystemExit('FAIL: build metadata commit mismatch')
if verify.get('pmCommitSha') != expected: raise SystemExit('FAIL: APK verification commit mismatch')
for name, item in (build.get('packages') or {}).items():
    if item.get('apkSha256'): resolve_artifact(name, item['apkSha256'], [root], item.get('apkFilename'))
print('PASS: same-SHA metadata and physical APK identities')
PY
            then artifact_verdict=PASS; else artifact_verdict=FAIL; reason='same-SHA APK artifact identity failed'; fi
            if [ "$artifact_verdict" = PASS ]; then
                rill_apk=$("$PY" -c "import json; r=json.load(open('$ARTIFACTS/build-metadata.json')); print(r['packages']['rill-runtime']['apkFilename'])")
                if [ ! -f "$ARTIFACTS/$rill_apk" ]; then artifact_verdict=FAIL; reason='exact rill-runtime APK filename is missing'; fi
            fi
        fi
    fi
fi

if [ "$artifact_verdict" != PASS ]; then
    runtime_verdict=BLOCKED; package_verdict=BLOCKED; service_verdict=BLOCKED
    ubus_verdict=BLOCKED; removal_verdict=BLOCKED; portable_verdict=BLOCKED
    report "$reason"; echo "BLOCKED: $reason"; exit 2
fi

if run_logged "$PORTABLE/portable-docker-gate.log" "$PY" scripts/portable_docker_gate.py \
    --expected-commit "$EXPECTED_SHA" --build-root "$ARTIFACTS" --ci-root "$INPUT/ci" \
    --docker-log "$DOCKER/core-runtime.log" --test-report "$SOURCE/test-report.json" \
    --out "$PORTABLE/portable-docker.json"; then
    portable_gate_verdict=PASS
else
    portable_gate_verdict=FAIL
    reason='existing portable_docker_gate.py failed same-SHA evidence checks'
fi

if run_logged "$DOCKER/runtime-v3.log" docker run --rm --privileged --platform "$DOCKER_PLATFORM" \
    -e PM_RILL_APK="/workspace/local-artifacts/x86_64/$rill_apk" \
    -v "$ROOT:/workspace" -w /workspace ubuntu:24.04 bash -lc \
    'set -eu; apt-get update >/dev/null; apt-get install -y --no-install-recommends python3 musl >/dev/null; rm -rf .portable-runtime-rootfs; cp -a .portable-rootfs .portable-runtime-rootfs; cp "$PM_RILL_APK" .portable-runtime-rootfs/tmp/; chroot .portable-runtime-rootfs /bin/sh -c "apk add --allow-untrusted --no-cache /tmp/$(basename "$PM_RILL_APK")"; LD_LIBRARY_PATH=/workspace/.portable-runtime-rootfs/lib:/workspace/.portable-runtime-rootfs/usr/lib:/lib:/usr/lib python3 scripts/rill_runtime_v3_integration.py --binary /workspace/.portable-runtime-rootfs/usr/bin/rill-runtime --out /workspace/local-evidence/docker/runtime-v3.json'; then runtime_verdict=PASS
else runtime_verdict=FAIL; reason='exact APK-installed Rill Runtime v3 integration failed'; fi

if [ "$runtime_verdict" = PASS ] && run_logged "$PACKAGE/package-composition.log" docker run --rm --privileged --platform "$DOCKER_PLATFORM" \
    -v "$ROOT:/workspace" -w /workspace ubuntu:24.04 bash -lc \
    "apt-get update >/dev/null && apt-get install -y --no-install-recommends python3 >/dev/null && python3 scripts/package_composition_gate.py --rootfs .portable-rootfs --packages local-artifacts/x86_64 --expected-commit $EXPECTED_SHA --openwrt-version 25.12.5 --target x86/64 --package-arch x86_64 --out local-evidence/package/package-composition.json"; then
    package_verdict=$("$PY" - "$PACKAGE/package-composition.json" <<'PY'
import json, sys
r = json.loads(open(sys.argv[1]).read())
matrices = list((r.get("matrices") or {}).values())
required = ("serviceSmoke", "ubusStatusSmoke", "rillStatusSmoke", "rillRemovalSmoke", "installedPayloadExact")
ok = bool(matrices) and r.get("verdict") == "PASS" and all(
    item.get("status") == "PASS" and all(item.get(field) is True for field in required)
    for item in matrices
)
print("PASS" if ok else "FAIL")
PY
)
    service_verdict=$("$PY" - "$PACKAGE/package-composition.json" <<'PY'
import json, sys
rows = list((json.loads(open(sys.argv[1]).read()).get("matrices") or {}).values())
print("PASS" if rows and all(row.get("status") == "PASS" and row.get("serviceSmoke") is True for row in rows) else "FAIL")
PY
)
    ubus_verdict=$("$PY" - "$PACKAGE/package-composition.json" <<'PY'
import json, sys
rows = list((json.loads(open(sys.argv[1]).read()).get("matrices") or {}).values())
print("PASS" if rows and all(row.get("status") == "PASS" and row.get("ubusStatusSmoke") is True and row.get("rillStatusSmoke") is True for row in rows) else "FAIL")
PY
)
    removal_verdict=$("$PY" - "$PACKAGE/package-composition.json" <<'PY'
import json, sys
rows = list((json.loads(open(sys.argv[1]).read()).get("matrices") or {}).values())
print("PASS" if rows and all(row.get("status") == "PASS" and row.get("rillRemovalSmoke") is True for row in rows) else "FAIL")
PY
)
else
    package_verdict=FAIL; service_verdict=FAIL; ubus_verdict=FAIL; removal_verdict=FAIL
    [ "$runtime_verdict" = PASS ] && reason='package composition or service smoke failed'
fi

if [ "$portable_gate_verdict" = PASS ] && [ "$runtime_verdict" = PASS ] && [ "$package_verdict" = PASS ] && [ "$service_verdict" = PASS ] && [ "$ubus_verdict" = PASS ] && [ "$removal_verdict" = PASS ]; then portable_verdict=PASS; else portable_verdict=FAIL; fi
report "${reason:-all local gates completed}"

if [ "$portable_verdict" = PASS ]; then echo 'PASS: MacBook + Docker portable validation'; exit 0; fi
echo "FAIL: ${reason:-portable validation failed}"; exit 1
