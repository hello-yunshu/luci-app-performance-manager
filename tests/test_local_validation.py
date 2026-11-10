import json
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import jsonschema


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/docker-validate/run-local-macos.sh"
SCHEMA = ROOT / "contracts/evidence/portable-macos-docker.schema.json"


class LocalValidationTests(unittest.TestCase):
    def test_mac_validation_script_exists_and_checks_docker(self):
        text = SCRIPT.read_text()
        self.assertTrue(SCRIPT.is_file())
        self.assertIn("docker version", text)
        self.assertIn("docker info", text)
        self.assertIn("docker-unavailable", text)

    def test_mac_validation_uses_amd64_and_verifies_rootfs_checksum(self):
        text = SCRIPT.read_text()
        self.assertIn("DOCKER_PLATFORM=linux/amd64", text)
        self.assertIn("sha256sums", text)
        self.assertIn("sha256sum -c", text)
        self.assertIn('grep -Eq "^[0-9a-f]{64}$"', text)
        self.assertIn("openwrt-25.12.5-x86-64-rootfs.tar.gz", text)
        self.assertIn(r"r'Ran (\d+) tests?'", text)

    def test_source_audit_normalizes_nondeterministic_temp_paths(self):
        text = (ROOT / "scripts/final_audit.py").read_text()
        self.assertIn("stable_output_tail", text)
        self.assertIn("<temporary-path>", text)

    def test_mac_validation_reuses_existing_gates_and_exact_artifact_identity(self):
        text = SCRIPT.read_text()
        for token in (
            "build-harness.py",
            "scripts/package_composition_gate.py",
            "scripts/portable_docker_gate.py",
            "scripts/verify_action_run_identity.py",
            "from artifact_identity import resolve_artifact",
            "repositoryCommitSha",
            "pmCommitSha",
        ):
            self.assertIn(token, text)

    def test_portable_evidence_cannot_authorize_stable_or_hardware(self):
        schema = json.loads(SCHEMA.read_text())
        self.assertEqual(schema["properties"]["profile"]["const"], "portable-macos-docker")
        self.assertEqual(schema["properties"]["hardwareCoverage"]["const"], "NOT_EVALUATED")
        self.assertIs(schema["properties"]["stableReleaseAuthorized"]["const"], False)
        sample = {
            "schemaVersion": 1,
            "profile": "portable-macos-docker",
            "pmCommitSha": "a" * 40,
            "host": {"os": "macOS", "architecture": "arm64"},
            "docker": {"platform": "linux/amd64", "version": "29"},
            "openwrt": {"version": "25.12.5", "target": "x86/64", "rootfsSha256": None},
            "sourceTests": "PASS", "coreRuntime": "BLOCKED", "runtimeV3": "BLOCKED",
            "packageComposition": "BLOCKED", "serviceSmoke": "BLOCKED", "ubusSmoke": "BLOCKED",
            "rillRemovalSmoke": "BLOCKED", "portableVerdict": "BLOCKED",
            "fullUpgrade": "BLOCKED", "pristineRootfs": "BLOCKED",
            "repositoryTransport": "NOT_EVALUATED", "transportVerdict": "BLOCKED",
            "hardwareCoverage": "NOT_EVALUATED", "stableReleaseAuthorized": False,
            "reason": "docker-unavailable", "artifact": {"identityVerdict": "NOT_EVALUATED"},
        }
        jsonschema.Draft202012Validator(schema).validate(sample)

    def test_hardware_aggregator_does_not_accept_mac_profile(self):
        text = (ROOT / "scripts/aggregate_stable_evidence.py").read_text()
        self.assertIn('choices=("hardware", "portable-docker")', text)
        self.assertNotIn("portable-macos-docker", text)

    def test_package_smoke_consumes_booleans_and_all_matrix_requirements(self):
        text = SCRIPT.read_text()
        self.assertIn("item.get(field) is True", text)
        self.assertIn('item.get("status") == "PASS"', text)
        self.assertIn('"installedPayloadExact"', text)

    def test_report_rejects_invalid_pass_invariants(self):
        common = [
            sys.executable, str(ROOT / "scripts/build_local_validation_report.py"),
            "--commit", "a" * 40, "--host-arch", "arm64", "--docker-version", "mock",
            "--source", "PASS", "--core", "PASS", "--runtime", "PASS",
            "--package", "PASS", "--service", "PASS", "--ubus", "PASS",
            "--removal", "PASS", "--portable", "PASS", "--artifact-identity", "PASS",
        ]
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "portable.json"
            null_sha = subprocess.run(
                common + ["--rootfs-sha", "", "--out", str(out)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(null_sha.returncode, 0)
            failed_service = subprocess.run(
                common + ["--rootfs-sha", "b" * 64, "--service", "FAIL", "--out", str(out)],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertNotEqual(failed_service.returncode, 0)

    def _mock_repo(self, directory: Path) -> tuple[Path, Path]:
        repo = directory / "repo"
        subprocess.run(["git", "clone", "--local", "--no-hardlinks", str(ROOT), str(repo)],
                       check=True, capture_output=True, text=True)
        for relative in (
            "tools/docker-validate/run-local-macos.sh",
            "scripts/build_local_validation_report.py",
            "contracts/evidence/portable-macos-docker.schema.json",
            "package/performance-manager/files/usr/share/performance-manager/schemas/portable-macos-docker.schema.json",
            "tests/test_all_in_one_package.py",
            "tests/test_local_validation.py",
            "tests/test_full_upgrade_gate.py",
            "scripts/package_composition_gate.py",
            "scripts/full_upgrade_gate.py",
            "scripts/portable_docker_gate.py",
            "scripts/build_synthetic_prior_fixture.py",
        ):
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        subprocess.run(["git", "add", "--"] + [
            "tools/docker-validate/run-local-macos.sh",
            "scripts/build_local_validation_report.py",
            "contracts/evidence/portable-macos-docker.schema.json",
            "package/performance-manager/files/usr/share/performance-manager/schemas/portable-macos-docker.schema.json",
            "tests/test_all_in_one_package.py",
            "tests/test_local_validation.py",
            "tests/test_full_upgrade_gate.py",
            "scripts/package_composition_gate.py",
            "scripts/full_upgrade_gate.py",
            "scripts/portable_docker_gate.py",
            "scripts/build_synthetic_prior_fixture.py",
        ], cwd=repo, check=True, capture_output=True, text=True)
        subprocess.run(["git", "-c", "user.name=portable-test", "-c",
                        "user.email=portable-test@example.invalid", "commit", "-m",
                        "test: mock portable closure", "--allow-empty"], cwd=repo, check=True,
                       capture_output=True, text=True)
        bin_dir = directory / "bin"
        bin_dir.mkdir()
        rootfs_sha = hashlib.sha256(b"mock-rootfs\n").hexdigest()
        package_report = {
            "schemaVersion": 1,
            "gate": "package-composition",
            "pmCommitSha": "PLACEHOLDER",
            "verdict": "PASS",
            "matrices": {
                label: {
                    "status": "PASS",
                    "serviceSmoke": True,
                    "ubusStatusSmoke": True,
                    "rillStatusSmoke": True,
                    "rillRemovalSmoke": True,
                    "fullRuntimeFaultSmoke": True,
                    "fullUninstallSmoke": True,
                    "fullRuntimeIdentity": True,
                    "packageConflictSmoke": True,
                    "installedPayloadExact": True,
                    "dependencyClosure": {
                        "timeoutPresentBeforeInstall": False,
                        "timeoutPresentAfterInstall": True,
                        "coreutilsTimeoutInstalled": True,
                        "resolvedByPackageManager": True,
                    },
                }
                for label in ("split", "all-in-one")
            },
            "pristineRootfs": {"pristineBeforeInstall": True},
            "repositoryTransport": "https",
            "fullUpgrade": {"verdict": "PASS", "transportVerdict": "PASS"},
        }
        docker = textwrap.dedent(f"""\
            #!/bin/sh
            set -eu
            args="$*"
            if [ "${{MOCK_DOCKER_UNAVAILABLE:-0}}" = 1 ]; then
              exit 1
            fi
            if echo "$args" | grep -q 'rootfs=openwrt-25.12.5-x86-64-rootfs.tar.gz'; then
              curl -o sha256sums https://downloads.openwrt.org/releases/25.12.5/targets/x86/64/sha256sums
              if [ ! -f openwrt-25.12.5-x86-64-rootfs.tar.gz ]; then
                curl -o openwrt-25.12.5-x86-64-rootfs.tar.gz https://downloads.openwrt.org/releases/25.12.5/targets/x86/64/openwrt-25.12.5-x86-64-rootfs.tar.gz
              fi
              if [ "${{MOCK_ROOTFS_MISMATCH:-0}}" = 1 ]; then
                echo 'FAIL: OpenWrt rootfs checksum mismatch'
                exit 1
              fi
              mkdir -p .portable-rootfs local-evidence/docker
              printf '{{"url":"mock","sha256":"{rootfs_sha}","verified":true}}\n' > local-evidence/docker/openwrt-rootfs-sha256.json
              exit 0
            fi
            if echo "$args" | grep -q -- '--entrypoint /bin/uname'; then
              echo x86_64
              exit 0
            fi
            if echo "$args" | grep -q -- 'alpine uname -m'; then
              if [ "${{MOCK_AMD64_UNAVAILABLE:-0}}" = 1 ]; then exit 1; fi
              echo x86_64
              exit 0
            fi
            if echo "$args" | grep -q -- 'package_composition_gate.py'; then
              mkdir -p local-evidence/package
              if [ "${{MOCK_PACKAGE_FALSE:-0}}" = 1 ]; then
                report='{json.dumps({**package_report, "matrices": {"split": {**package_report["matrices"]["split"], "serviceSmoke": False}, "all-in-one": package_report["matrices"]["all-in-one"]}}).replace("PLACEHOLDER", "PLACEHOLDER")}'
              else
                report='{json.dumps(package_report)}'
              fi
              printf '%s\\n' "$report" | sed "s/PLACEHOLDER/$(git rev-parse HEAD)/g" > local-evidence/package/package-composition.json
              exit 0
            fi
            if echo "$args" | grep -q -- 'rill_runtime_v3_integration.py'; then
              echo 'RUNTIME_V3_PASS'
              exit 0
            fi
            if echo "$args" | grep -q -- '/usr/bin/ucode'; then
              echo 'UCODE_HARNESS_PASS'
              exit 0
            fi
            if [ "$1" = version ] || [ "$1" = info ]; then
              echo 'mock docker'
              exit 0
            fi
            if [ "$1" = build ]; then
              exit 0
            fi
            echo "unexpected docker invocation: $args" >&2
            exit 1
        """)
        curl = textwrap.dedent(f"""\
            #!/bin/sh
            set -eu
            out=''
            while [ "$#" -gt 0 ]; do
              if [ "$1" = -o ]; then out="$2"; shift 2; continue; fi
              shift
            done
            test -n "$out"
            printf '%s\\n' "$out" >> "${{MOCK_CURL_LOG:-curl-calls.log}}"
            case "$out" in
              *sha256sums) printf '%s  *openwrt-25.12.5-x86-64-rootfs.tar.gz\\n' '{rootfs_sha}' > "$out" ;;
              *) printf 'mock-rootfs\\n' > "$out" ;;
            esac
        """)
        gh = textwrap.dedent("""\
            #!/bin/sh
            set -eu
            sha=$(git rev-parse HEAD)
            if [ "${MOCK_GH_UNAVAILABLE:-0}" = 1 ]; then
              [ "$1" = run ] && [ "$2" = list ] && printf '[]\\n' && exit 0
            fi
            if [ "$1" = run ] && [ "$2" = list ]; then
              case "$*" in
                *build-openwrt.yml*) printf '[{"databaseId":100,"status":"completed","conclusion":"success","headSha":"%s"}]\\n' "$sha" ;;
                *) printf '[{"databaseId":200,"status":"completed","conclusion":"success","headSha":"%s"}]\\n' "$sha" ;;
              esac
              exit 0
            fi
            if [ "$1" = api ]; then
              case "$2" in
                */100) name='Build OpenWrt (remote SDK)'; path='.github/workflows/build-openwrt.yml'; id=11 ;;
                *) name='CI'; path='.github/workflows/ci.yml'; id=22 ;;
              esac
              printf '{"conclusion":"success","head_sha":"%s","name":"%s","path":"%s","workflow_id":%s,"run_attempt":1,"event":"push","head_branch":"yunshu/openwrt-reaudit","repository":{"full_name":"hello-yunshu/luci-app-performance-manager"}}\\n' "$sha" "$name" "$path" "$id"
              exit 0
            fi
            if [ "$1" = run ] && [ "$2" = download ]; then
              run_id="$3"
              shift 3
              out=''
              while [ "$#" -gt 0 ]; do
                if [ "$1" = --dir ]; then out="$2"; shift 2; continue; fi
                shift
              done
              mkdir -p "$out"
              if [ "$run_id" = 100 ]; then
                python3 - "$out" "$sha" <<'PY'
            import hashlib, json, sys
            from pathlib import Path
            out, commit = Path(sys.argv[1]), sys.argv[2]
            root = out / 'x86-64-x86_64-packages-and-evidence'
            (root / 'docs').mkdir(parents=True)
            names = ('performance-manager', 'luci-app-performance-manager', 'performance-manager-rill', 'rill-runtime', 'luci-app-performance-manager-all')
            packages = {}
            for name in names:
                path = root / ('nested-sdk/base' if name == 'rill-runtime' else '') / f'{name}-mock.apk'
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(name.encode())
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                packages[name] = {'status': 'ok', 'apkFilename': path.name, 'apkSha256': digest, 'pkgver': '1', 'installedPayload': {}}
            packages['luci-app-performance-manager-all'].update({'arch': 'x86_64'})
            packages['luci-app-performance-manager-all']['runtimeBinary'] = {'status': 'present', 'matchesSplitRuntime': True, 'sha256': 'a' * 64}
            build = {'verdict': 'PASS', 'repositoryCommitSha': commit, 'architecture': 'x86_64',
                     'target': 'x86/64', 'rillConsumedVersion': '1.5.6',
                     'externalRuntime': {'commit': 'b' * 40}, 'fullPackage': {'runtimeBundled': True},
                     'packages': packages}
            (root / 'build-metadata.json').write_text(json.dumps(build))
            verified = {name: {'status': 'ok', 'sha256': item['apkSha256'], 'arch': 'x86_64' if name == 'luci-app-performance-manager-all' else 'noarch'} for name, item in packages.items()}
            verified['luci-app-performance-manager-all']['runtimeBinary'] = packages['luci-app-performance-manager-all']['runtimeBinary']
            (root / 'docs/apk-verification.json').write_text(json.dumps({'verdict': 'PASS', 'pmCommitSha': commit, 'arch': 'x86_64', 'packages': verified}))
            PY
              else
                printf '{"expectedCommitSha":"%s","overallVerdict":"PASS"}\\n' "$sha" > "$out/final-release-evidence.json"
              fi
              exit 0
            fi
            echo "unexpected gh invocation: $*" >&2
            exit 1
        """)
        for name, content in (("docker", docker), ("curl", curl), ("gh", gh)):
            path = bin_dir / name
            path.write_text(content)
            path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return repo, bin_dir

    def _restore_audit_outputs(self, repo: Path) -> None:
        for relative in (
            "docs/FINAL_AUDIT.json", "docs/FINAL_AUDIT.md", "docs/HOST_SYNTAX_REPORT.json",
            "docs/RESOURCE_BUDGET.json", "docs/source-audit.json",
        ):
            original = subprocess.check_output(["git", "show", f"HEAD:{relative}"], cwd=repo)
            (repo / relative).write_bytes(original)

    def test_mock_full_success_and_cache_then_boolean_failure(self):
        if os.environ.get("PM_ORCHESTRATOR_TEST"):
            return
        with tempfile.TemporaryDirectory() as directory:
            repo, bin_dir = self._mock_repo(Path(directory))
            env = os.environ.copy()
            for key in ("PM_BUILD_RUN_ID", "PM_CI_RUN_ID", "PM_EXPECTED_SHA"):
                env.pop(key, None)
            env.update({
                "PATH": f"{bin_dir}:{env['PATH']}",
                "PM_VALIDATION_PYTHON": sys.executable,
                "PM_ORCHESTRATOR_TEST": "1",
                "MOCK_CURL_LOG": str(Path(directory) / "curl-calls.log"),
            })
            first = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                   cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            report = json.loads((repo / "local-evidence/portable/portable-macos-docker.json").read_text())
            self.assertEqual(report["portableVerdict"], "PASS")
            self.assertEqual(report["hardwareCoverage"], "NOT_EVALUATED")
            self.assertFalse(report["stableReleaseAuthorized"])
            self.assertRegex(report["openwrt"]["rootfsSha256"], r"^[0-9a-f]{64}$")
            self.assertIn("--entrypoint /bin/uname", (repo / "tools/docker-validate/run-local-macos.sh").read_text())
            self.assertEqual((Path(directory) / "curl-calls.log").read_text().splitlines(), ["sha256sums", "openwrt-25.12.5-x86-64-rootfs.tar.gz"])
            self._restore_audit_outputs(repo)

            second = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                    cwd=repo, env={**env, "MOCK_PACKAGE_FALSE": "1"},
                                    capture_output=True, text=True)
            self.assertEqual(second.returncode, 1, second.stdout + second.stderr)
            failed = json.loads((repo / "local-evidence/portable/portable-macos-docker.json").read_text())
            self.assertEqual(failed["packageComposition"], "FAIL")
            self.assertEqual(failed["portableVerdict"], "FAIL")
            self.assertEqual((Path(directory) / "curl-calls.log").read_text().splitlines(), [
                "sha256sums", "openwrt-25.12.5-x86-64-rootfs.tar.gz", "sha256sums"
            ])

    def test_mock_checksum_mismatch_is_fail_and_missing_same_sha_is_blocked(self):
        if os.environ.get("PM_ORCHESTRATOR_TEST"):
            return
        with tempfile.TemporaryDirectory() as directory:
            repo, bin_dir = self._mock_repo(Path(directory))
            env = os.environ.copy()
            for key in ("PM_BUILD_RUN_ID", "PM_CI_RUN_ID", "PM_EXPECTED_SHA"):
                env.pop(key, None)
            env.update({
                "PATH": f"{bin_dir}:{env['PATH']}",
                "PM_VALIDATION_PYTHON": sys.executable,
                "PM_ORCHESTRATOR_TEST": "1",
                "MOCK_CURL_LOG": str(Path(directory) / "curl-calls.log"),
                "MOCK_ROOTFS_MISMATCH": "1",
            })
            mismatch = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                      cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(mismatch.returncode, 1, mismatch.stdout + mismatch.stderr)
            self.assertIn("FAIL:", mismatch.stdout)
            self._restore_audit_outputs(repo)

            env.pop("MOCK_ROOTFS_MISMATCH")
            env["MOCK_GH_UNAVAILABLE"] = "1"
            blocked = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                     cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(blocked.returncode, 2, blocked.stdout + blocked.stderr)
            self.assertIn("BLOCKED:", blocked.stdout)

            self._restore_audit_outputs(repo)
            env.pop("MOCK_GH_UNAVAILABLE")
            env["MOCK_DOCKER_UNAVAILABLE"] = "1"
            docker_blocked = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                            cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(docker_blocked.returncode, 2, docker_blocked.stdout + docker_blocked.stderr)
            self.assertIn("docker-unavailable", docker_blocked.stdout)

            self._restore_audit_outputs(repo)
            env.pop("MOCK_DOCKER_UNAVAILABLE")
            env["MOCK_AMD64_UNAVAILABLE"] = "1"
            amd64_blocked = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                           cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(amd64_blocked.returncode, 2, amd64_blocked.stdout + amd64_blocked.stderr)
            self.assertIn("BLOCKED:", amd64_blocked.stdout)

    def test_dirty_worktree_states_fail_but_ignored_evidence_does_not(self):
        if os.environ.get("PM_ORCHESTRATOR_TEST"):
            return
        with tempfile.TemporaryDirectory() as directory:
            repo, bin_dir = self._mock_repo(Path(directory))
            env = os.environ.copy()
            for key in ("PM_BUILD_RUN_ID", "PM_CI_RUN_ID", "PM_EXPECTED_SHA"):
                env.pop(key, None)
            env.update({"PATH": f"{bin_dir}:{env['PATH']}", "PM_VALIDATION_PYTHON": sys.executable,
                        "PM_ORCHESTRATOR_TEST": "1"})
            mismatch = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                      cwd=repo, env={**env, "PM_EXPECTED_SHA": "a" * 40},
                                      capture_output=True, text=True)
            self.assertEqual(mismatch.returncode, 1)
            self.assertIn("HEAD mismatch", mismatch.stdout)
            (repo / "tracked-dirty.txt").write_text("dirty\n")
            subprocess.run(["git", "add", "tracked-dirty.txt"], cwd=repo, check=True)
            staged = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                    cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(staged.returncode, 1)
            self.assertIn("dirty-worktree", staged.stdout)

            subprocess.run(["git", "reset", "--quiet", "HEAD", "--", "tracked-dirty.txt"], cwd=repo, check=True)
            (repo / "tracked-dirty.txt").unlink()
            (repo / "source-untracked.txt").write_text("source\n")
            untracked = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                       cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(untracked.returncode, 1)
            self.assertIn("dirty-worktree", untracked.stdout)

            (repo / "source-untracked.txt").unlink()
            (repo / "local-evidence").mkdir(exist_ok=True)
            (repo / "local-evidence/ignored.json").write_text("{}\n")
            ignored = subprocess.run([str(repo / "tools/docker-validate/run-local-macos.sh")],
                                     cwd=repo, env={**env, "MOCK_GH_UNAVAILABLE": "1"},
                                     capture_output=True, text=True)
            self.assertNotEqual(ignored.returncode, 1)
            self.assertNotIn("dirty-worktree", ignored.stdout)
