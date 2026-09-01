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
        self.assertIn('os.environ.get("GITHUB_SHA", "")', audit)
        self.assertIn('re.fullmatch(r"[0-9a-f]{40}", workflow_sha)', audit)

    def test_ci_aggregator_resolves_unique_artifact_layouts(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("rill-runtime-v3:", workflow)
        self.assertIn("rill_runtime_v3_integration.py", workflow)
        self.assertIn("check_rill_dependency.py --package-dir", workflow)

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
            "rillMaxRssKiB": "B_RILL_RSS",
            "coreMeanCpuPercent": "B_CORE_CPU",
            "rillMeanCpuPercent": "B_RILL_CPU",
            "pmPersistentWritesPerDay": "B_PM_WRITES_DAY",
            "rillStateFileMaxBytes": "B_RILL_STATE_BYTES",
            "bindingHighWater": "B_BINDINGS",
            "persistentHistoryGrowthBytes": "B_HISTORY_GROWTH",
        }
        for key, variable in expected.items():
            with self.subTest(key=key):
                self.assertIn(f"{variable}={budget[key]}", script)



class ContractTests(unittest.TestCase):
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

    def test_openwrt_download_caches_remain_digest_bound_and_fail_closed(self):
        cache_action = "actions/cache@v6"
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        build = (ROOT / ".github/workflows/build-openwrt.yml").read_text()

        self.assertEqual(ci.count(cache_action), 0)
        self.assertIn("git -C rill-ml fetch --depth=1 origin \"$commit\"", ci)
        self.assertIn("cargo build --locked --release --manifest-path rill-ml/Cargo.toml -p rill-runtime", ci)
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
    def test_action_contract_requires_frozen_safety_fields(self):
        sch=json.loads((ROOT/'contracts/action.schema.json').read_text())
        for field in ['risk','requiresBenchmark','persistenceClass','commitPolicy','requiredLocks','requiresCommitConfirm']:
            self.assertIn(field,sch['required'])
    def test_transaction_states_cover_full_frozen_machine(self):
        states=set(json.loads((ROOT/'contracts/transaction.schema.json').read_text())['properties']['state']['enum'])
        self.assertEqual(states,{'planned','locked','snapshotted','pending','applied','verified','awaiting_confirm','committed','rolled_back','failed'})
if __name__=='__main__': unittest.main()
