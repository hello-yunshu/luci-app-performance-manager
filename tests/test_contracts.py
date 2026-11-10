import json
import re
import unittest
from pathlib import Path
import jsonschema

ROOT=Path(__file__).resolve().parents[1]
PAIRS={
 'action.example.json':'action.schema.json','fastpath-action.example.json':'action.schema.json',
 'target-ref.example.json':'target-ref.schema.json','capability.example.json':'capability.schema.json',
 'topology-path.example.json':'topology-path.schema.json','transaction.example.json':'transaction.schema.json',
 'rill-ipc.example.json':'rill-ipc.schema.json','profile.schema.example.json':'profile.schema.json',
 'persistence.example.json':'persistence.schema.json','lock.example.json':'lock.schema.json','health.example.json':'health.schema.json',
 'benchmark-session.example.json':'benchmark-session.schema.json','companion-measurement.example.json':'companion-measurement.schema.json',
}
class ResourceBudgetTests(unittest.TestCase):
    def test_source_audit_uses_exact_workflow_head_identity(self):
        audit = (ROOT / "scripts/final_audit.py").read_text()
        self.assertIn('def head_sha()', audit)
        self.assertIn('git_output(["rev-parse", "HEAD"])', audit)
        self.assertIn('SOURCE_COMMIT = source_commit(HEAD_SHA)', audit)
        self.assertIn('dirty_source_paths()', audit)
        self.assertIn('GENERATED_EVIDENCE_PATHS', audit)
        self.assertNotIn('WORKTREE_UNCOMMITTED', audit)

    def test_core_reports_actionable_ubus_startup_failures(self):
        core = (ROOT / "package/performance-manager/files/usr/sbin/performance-manager.uc").read_text()
        for code in ("ubus-socket-unavailable", "ubus-permission-denied",
                     "state-dir-not-writable", "ubus-publish-failed"):
            with self.subTest(code=code):
                self.assertIn(code, core)
        self.assertNotIn("unable to connect to ubus", core)
        self.assertLess(core.index("ensure_dir(`${persist_dir()}/rill-executions`)"),
                        core.index("let dir_issue = runtime_dir_diagnosis()"))
        self.assertLess(core.index("if (dir_issue)"), core.index("let obj = conn.publish("))

    def test_ci_aggregator_resolves_unique_artifact_layouts(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("rill-runtime-v3:", workflow)
        self.assertIn("rill_runtime_v3_integration.py", workflow)
        self.assertIn("check_rill_dependency.py --package-dir", workflow)
        self.assertIn("actions/download-artifact@v8", workflow)
        self.assertIn("rill-runtime-input/rill-runtime", workflow)
        self.assertNotIn("Build the exact pinned Runtime binary", workflow)

    def test_resource_budget_requires_target_and_soak_evidence(self):
        script = (ROOT / "scripts/resource_budget.py").read_text()
        self.assertIn("scripts/openwrt-target-gate.sh", script)
        self.assertIn("scripts/openwrt-resource-soak.sh", script)
        self.assertNotIn("'requiredScript':'scripts/openwrt-runtime-smoke.sh'", script)

    def test_resource_soak_short_run_cannot_claim_stable_pass(self):
        script = (ROOT / "scripts/openwrt-resource-soak.sh").read_text()
        self.assertIn('"stableDurationSatisfied": $stable', script)
        self.assertIn('"passed": $within', script)
        self.assertIn('[ "$stable" = true ] || within=false', script)
        self.assertIn('measurementUnavailable', script)
        self.assertIn('[ "$runtime_failures" -eq 0 ]', script)
        self.assertNotIn('deliberately does not invent', script)

    def test_resource_soak_never_zero_fills_missing_rill_measurements(self):
        script = (ROOT / "scripts/openwrt-resource-soak.sh").read_text()
        self.assertNotIn("detail.persistentWrites", script)
        self.assertIn("blocked core-pid-unavailable", script)
        self.assertIn("blocked rill-runtime-sha-unavailable", script)

    def test_precommitted_resource_budgets_match_target_gate(self):
        budget = json.loads((ROOT / "docs/RESOURCE_BUDGET.json").read_text())["precommittedStableBudgets"]
        script = (ROOT / "scripts/openwrt-resource-soak.sh").read_text()
        expected = {
            "coreMaxRssKiB": "B_CORE_RSS",
            "coreMeanCpuPercent": "B_CORE_CPU",
            "pmPersistentWritesPerDay": "B_PM_WRITES_DAY",
            "runtimeStateMaxBytes": "B_RUNTIME_STATE_BYTES",
            "bindingHighWater": "B_BINDINGS",
            "persistentHistoryGrowthBytes": "B_HISTORY_GROWTH",
        }
        for key, variable in expected.items():
            with self.subTest(key=key):
                self.assertIn(f"{variable}={budget[key]}", script)

    def test_resource_soak_contract_uses_runtime_names_only(self):
        schema = (ROOT / "contracts/evidence/resource-soak.schema.json").read_text()
        evaluator = (ROOT / "scripts/validate_external_evidence.py").read_text()
        for text in (schema, evaluator):
            self.assertIn("idleExpectedRuntimePersistenceEventsDelta", text)
            self.assertNotIn("idleExpectedAdapterPersistenceEventsDelta", text)
            self.assertNotIn("idleAdapterPersistenceZero", text)
        self.assertNotIn("rillRssKiB", schema + evaluator)
        self.assertNotIn("rillRestartCount", schema + evaluator)

    def test_resource_soak_has_its_own_timeout_budget(self):
        workflow = (ROOT / ".github/workflows/hardware-validation.yml").read_text()
        self.assertIn("timeout-minutes: ${{ matrix.timeout }}", workflow)
        self.assertIn("runner: pm-soak\n            timeout: 1800", workflow)
        self.assertIn("runner: pm-generic\n            timeout: 1440", workflow)



class ContractTests(unittest.TestCase):
    def test_production_and_harness_share_the_locked_v3_envelope_shape(self):
        core = (ROOT / 'package/performance-manager/files/usr/sbin/performance-manager.uc').read_text()
        harness = (ROOT / 'scripts/rill_runtime_v3_integration.py').read_text()
        required = ['requestId', 'apiVersion', 'clientIdentity', 'modelGeneration',
                    'stateGeneration', 'payloadLimit', 'request']
        for field in required:
            with self.subTest(field=field):
                self.assertIn(field + ':' if field != 'request' else 'request.request', core)
                self.assertIn('"' + field + '"', harness)
        self.assertIn('featureSchemaHash', core)
        self.assertIn('featureSchemaHash', harness)
        self.assertIn('"featureSchemaHash": schema_hash', harness)
        self.assertNotIn('partitionKey', core)
        self.assertNotIn('partitionKey', harness)
        self.assertNotIn('clientIdentityName', core[core.index('let request = {'):core.index("if (op == 'status')")])

    def test_github_actions_follow_readable_refs(self):
        expected = {
            "actions/checkout": "v7",
            "actions/setup-python": "v7",
            "actions/cache": "v6",
            "actions/upload-artifact": "v7",
            "actions/download-artifact": "v8",
        }
        found = set()
        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            for action, ref in re.findall(r"uses:\s*(actions/[\w-]+)@([^\s]+)", workflow.read_text()):
                found.add(action)
                self.assertEqual(ref, expected[action], f"{workflow.name}: {action}")
                self.assertRegex(ref, r"^v[0-9]+$")
        self.assertEqual(found, set(expected))

    def test_sync_rill_is_read_only_and_cannot_create_branches(self):
        workflow = (ROOT / ".github/workflows/sync-rill.yml").read_text()
        self.assertIn("contents: read", workflow)
        self.assertIn("pull-requests: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("pull-requests: write", workflow)
        self.assertNotIn("git switch -c", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("gh pr create", workflow)

    def test_openwrt_download_caches_remain_digest_bound_and_fail_closed(self):
        cache_action = "actions/cache@v6"
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        build = (ROOT / ".github/workflows/build-openwrt.yml").read_text()

        self.assertEqual(ci.count(cache_action), 0)
        self.assertIn('git -C rill-openwrt-packages fetch --depth=1 origin "$package_commit"', ci)
        self.assertIn('test "$(git -C rill-openwrt-packages rev-parse HEAD)" = "$package_commit"', ci)
        self.assertIn('scripts/qualified_runtime_artifacts.py', ci)
        self.assertIn('--channel stable --contract', ci)
        self.assertIn('.qualifiedTarget.binarySha256', ci)
        self.assertNotIn('cargo build', ci)
        rootfs = (ROOT / 'scripts/prepare_runtime_test_rootfs.sh').read_text()
        self.assertIn('sha256sum -c -', rootfs)
        self.assertIn('test "${#digests[@]}" -eq 1', rootfs)
        self.assertIn("openwrt-sdk-${{ runner.os }}-${{ runner.arch }}", build)
        self.assertIn("openwrt-feeds-${{ runner.os }}-${{ runner.arch }}", build)
        self.assertIn("$SDK_ARCHIVE_SHA256\" \"$archive\" | sha256sum -c -", build)
        self.assertNotIn("bin/packages", "\n".join(
            line for line in build.splitlines() if "key: openwrt-" in line
        ))

    def test_all_examples_validate(self):
        for example,schema in PAIRS.items():
            with self.subTest(example=example):
                obj=json.loads((ROOT/'schemas'/example).read_text()); sch=json.loads((ROOT/'contracts'/schema).read_text())
                jsonschema.Draft202012Validator(sch).validate(obj)
    def test_rill_ipc_runtime_v3_branches_enforce_method_binding(self):
        sch=json.loads((ROOT/'contracts/rill-ipc.schema.json').read_text())
        v=jsonschema.Draft202012Validator(sch)
        decide=json.loads((ROOT/'schemas/rill-ipc.example.json').read_text())
        self.assertTrue(v.is_valid(decide))
        self.assertFalse(v.is_valid({**decide,'apiVersion':2}))
        self.assertFalse(v.is_valid({**decide,'request':{**decide['request'],'method':'health'}}))
        self.assertFalse(v.is_valid({**decide,'unexpected':True}))
        self.assertFalse(v.is_valid({k:value for k,value in decide.items() if k!='featureSchemaHash'}))
    def test_rill_ipc_feedback_requires_decision_and_reward_fields(self):
        sch=json.loads((ROOT/'contracts/rill-ipc.schema.json').read_text())
        v=jsonschema.Draft202012Validator(sch)
        feedback=json.loads((ROOT/'schemas/rill-ipc.example.json').read_text())
        feedback['request']={'method':'feedback','decisionId':'d1','selectedActionId':'pm.noop','reward':0.0,'outcomeTimeMs':1,'generation':0}
        self.assertTrue(v.is_valid(feedback))
        for field in ['decisionId','selectedActionId','reward','outcomeTimeMs','generation']:
            with self.subTest(field=field):
                broken=json.loads(json.dumps(feedback)); del broken['request'][field]
                self.assertFalse(v.is_valid(broken),f'feedback must reject missing {field}')
    def test_rill_ipc_response_is_generic_runtime_v3(self):
        schema=json.loads((ROOT/'contracts/rill-ipc-response.schema.json').read_text())
        v=jsonschema.Draft202012Validator(schema)
        base={'requestId':'d1','apiVersion':3,'runtimeIdentity':{'name':'rill-runtime','version':'1.5.6'},'modelGeneration':2,'stateGeneration':1}
        handshake={**base,'response':{'kind':'handshake','capabilities':['org.rill.preview.decide'],'featureSchemaHash':'9'*64,'handlerApiVersion':2}}
        self.assertTrue(v.is_valid(handshake))
        result={**base,'response':{'kind':'result','output':{'accepted':True,'selectedActionId':'pm.noop','scores':[]}}}
        self.assertTrue(v.is_valid(result))
        unknown=json.loads(json.dumps(result)); unknown['response']['extra']=True
        self.assertFalse(v.is_valid(unknown))
    def test_runtime_package_has_every_formal_schema(self):
        dest=ROOT/'package/performance-manager/files/usr/share/performance-manager/schemas'
        for schema in sorted((ROOT/'contracts').glob('*.schema.json')):
            with self.subTest(schema=schema.name):
                self.assertTrue((dest/schema.name).exists())
                self.assertEqual(json.loads(schema.read_text()),json.loads((dest/schema.name).read_text()))

    def test_contracts_are_the_only_active_schema_source(self):
        active_ids = {}
        for schema in sorted((ROOT / 'contracts').glob('*.schema.json')):
            data = json.loads(schema.read_text())
            schema_id = data.get('$id')
            if schema_id:
                self.assertNotIn(schema_id, active_ids, schema_id)
                active_ids[schema_id] = schema.name
        self.assertFalse(list((ROOT / 'schemas').glob('*.schema.json')))
    def test_action_contract_requires_frozen_safety_fields(self):
        sch=json.loads((ROOT/'contracts/action.schema.json').read_text())
        for field in ['risk','requiresBenchmark','persistenceClass','commitPolicy','requiredLocks','requiresCommitConfirm']:
            self.assertIn(field,sch['required'])
    def test_transaction_states_cover_full_frozen_machine(self):
        states=set(json.loads((ROOT/'contracts/transaction.schema.json').read_text())['properties']['state']['enum'])
        self.assertEqual(states,{'planned','locked','snapshotted','pending','applied','verified','awaiting_confirm','committed','rolled_back','failed'})
class AuditConvergenceTests(unittest.TestCase):
    def test_single_authoritative_rill_contract(self):
        contract = json.loads((ROOT / "contracts/rill-runtime.json").read_text())
        self.assertEqual(contract.get("schemaVersion"), 1)
        for section in ("runtime", "protocol", "security", "resolved", "openwrtPackage", "qualification"):
            with self.subTest(section=section):
                self.assertIn(section, contract)
        self.assertFalse((ROOT / "contracts/rill-dependency.json").exists())
        for scope in ("scripts", ".github", "package"):
            for path in (ROOT / scope).rglob("*"):
                if path.is_file() and path.suffix in (".py", ".json", ".yml", ".yaml", ".uc", ".sh", ".js"):
                    with self.subTest(path=str(path)):
                        self.assertNotIn("rill-dependency", path.read_text(errors="ignore"))

    def test_contract_check_records_release_pin_structure_verdict(self):
        import importlib.util
        import sys
        sys.path.insert(0, str(ROOT / "scripts"))
        spec = importlib.util.spec_from_file_location(
            "rill_contract_check", ROOT / "scripts/rill_contract_check.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        contract = json.loads((ROOT / "contracts/rill-runtime.json").read_text())
        verdict, checks = module.release_pin_structure(contract)
        self.assertEqual(verdict, "PASS")
        self.assertTrue(all(check["ok"] for check in checks))
        broken = json.loads(json.dumps(contract))
        broken["openwrtPackage"]["commit"] = "not-a-sha"
        broken["openwrtPackage"]["packageRelease"] = 0
        broken["qualification"]["verdict"] = "BLOCKED"
        broken["resolved"]["upstreamCommit"] = "main"
        self.assertEqual(module.release_pin_structure(broken)[0], "FAIL")
        status = json.loads((ROOT / "docs/rill-integration-status.json").read_text())
        self.assertEqual(status.get("releasePinStructureVerdict"), "PASS")
        pin = status.get("releasePin", {})
        self.assertEqual(pin.get("commit"), contract["openwrtPackage"]["commit"])
        self.assertEqual(pin.get("packageRelease"), contract["openwrtPackage"]["packageRelease"])
        self.assertEqual(pin.get("qualification", {}).get("runId"), contract["qualification"]["runId"])
        self.assertEqual(pin.get("resolvedVersion"), contract["resolved"]["version"])

    def test_final_evidence_carries_contract_pin(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "aggregate_final_evidence", ROOT / "scripts/aggregate_final_evidence.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        contract = json.loads((ROOT / "contracts/rill-runtime.json").read_text())
        pin = module.contract_pin(ROOT / "contracts/rill-runtime.json")
        self.assertTrue(pin["available"])
        self.assertEqual(pin["commit"], contract["openwrtPackage"]["commit"])
        self.assertEqual(pin["packageRelease"], contract["openwrtPackage"]["packageRelease"])
        self.assertEqual(pin["qualification"]["runId"], contract["qualification"]["runId"])
        self.assertEqual(pin["resolvedVersion"], contract["resolved"]["version"])

    def test_docs_do_not_claim_sha_pinned_actions(self):
        status = (ROOT / "docs/IMPLEMENTATION_STATUS.md").read_text()
        self.assertNotIn("pinned to SHAs", status)
        self.assertIn("readable major tags", status)

    def test_roadmap_job_names_match_workflows(self):
        roadmap = (ROOT / "ROADMAP.md").read_text()
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        build = (ROOT / ".github/workflows/build-openwrt.yml").read_text()
        for job in ("static", "rill-runtime-v3", "production-core-rill-integration"):
            with self.subTest(job=job):
                self.assertIn(f"\n  {job}:", ci)
                self.assertIn(f"`{job}`", roadmap)
        self.assertIn("\n  openwrt-sdk-build:", build)
        self.assertIn("`openwrt-sdk-build`", roadmap)
        for stale in ("pm-rill-provenance", "pm-rill-runtime", "pm-core-rill-roundtrip", "openwrt-ucode"):
            with self.subTest(stale=stale):
                self.assertNotIn(stale, roadmap)

    def test_test_plan_gates_are_executable_in_repo(self):
        plan = (ROOT / "docs/TEST_PLAN.md").read_text()
        self.assertNotIn("cargo test", plan)
        self.assertNotIn("cargo check", plan)
        self.assertIn("make audit", plan)
        self.assertIn("scripts/luci_render_smoke.js", plan)
        self.assertIn("tools/docker-validate/run-target-gate.sh", plan)
        self.assertIn("scripts/rill_runtime_v3_integration.py", plan)
        self.assertIn("scripts/production_core_rill_integration.py", plan)
        self.assertIn("openwrt-sdk-build", plan)

    def test_historical_rill_evidence_is_labelled(self):
        provenance = json.loads((ROOT / "docs/rill-provenance.json").read_text())
        self.assertEqual(provenance.get("evidenceStatus"), "historical-only")
        self.assertEqual(provenance.get("supersededBy"), "contracts/rill-runtime.json")
        contract = json.loads((ROOT / "contracts/rill-runtime.json").read_text())
        self.assertEqual(contract["resolved"]["version"], "1.5.6")

    def test_profile_badge_has_distinct_unhealthy_state(self):
        ui = (ROOT / "package/luci-app-performance-manager/htdocs/luci-static/resources/view/performance-manager/overview.js").read_text()
        self.assertIn("_('Profile unmet')", ui)
        self.assertIn("profile.degraded", ui)
        self.assertIn("_('Profile degraded')", ui)
        self.assertIn("_('Profile healthy')", ui)
        self.assertNotIn("profile.healthy ? _('Profile healthy') : _('Profile degraded')", ui)


    def test_harness_strips_multiline_ubus_startup_guard(self):
        import subprocess
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "harness.uc"
            subprocess.run(
                ["python3", str(ROOT / "tools/docker-validate/harness/build-harness.py"),
                 str(out), str(ROOT / "tools/docker-validate/harness/production_core_rill_test.uc.frag")],
                check=True, capture_output=True, text=True)
            text = out.read_text()
        # The library must load without a real ubus daemon: the ambient connect
        # and its multi-line fail-closed guard are both neutralised.
        self.assertNotIn("ubusmod.connect()", text)
        self.assertNotIn("if (!conn)", text)
        self.assertIn("function diagnostics(", text)


if __name__=='__main__': unittest.main()
