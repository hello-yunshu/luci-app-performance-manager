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
        self.assertIn("copy_unique_evidence rill-runtime.json required", workflow)
        self.assertIn('mapfile -t matches < <(find evidence -type f -name "$name" -print)', workflow)

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
        self.assertIn("blocked rill-pid-unavailable", script)
        self.assertIn("blocked rill-adapter-sha-unavailable", script)

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
    def test_github_actions_follow_immutable_full_sha_pins(self):
        expected = {
            "actions/checkout": "3d3c42e5aac5ba805825da76410c181273ba90b1",
            "actions/setup-python": "5fda3b95a4ea91299a34e894583c3862153e4b97",
            "actions/cache": "55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
            "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
        }
        found = set()
        for workflow in (ROOT / ".github/workflows").glob("*.yml"):
            for action, ref in re.findall(r"uses:\s*(actions/[\w-]+)@([^\s]+)", workflow.read_text()):
                found.add(action)
                self.assertEqual(ref, expected[action], f"{workflow.name}: {action}")
                self.assertRegex(ref, r"^[0-9a-f]{40}$")
        self.assertEqual(found, set(expected))

    def test_openwrt_download_caches_remain_digest_bound_and_fail_closed(self):
        cache_action = "actions/cache@55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        build = (ROOT / ".github/workflows/build-openwrt.yml").read_text()

        self.assertEqual(ci.count(cache_action), 3)
        self.assertEqual(ci.count("openwrt-rootfs-${{ runner.os }}-${{ runner.arch }}"), 3)
        self.assertEqual(ci.count("$OPENWRT_ROOTFS_SHA256\" \"$archive\" | sha256sum -c -"), 3)
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
    def test_rill_ipc_per_op_branches_enforce_full_context_binding(self):
        sch=json.loads((ROOT/'contracts/rill-ipc.schema.json').read_text())
        v=jsonschema.Draft202012Validator(sch)
        # The schema is oneOf over per-op $defs with additionalProperties:false,
        # mirroring the tagged Request enum (deny_unknown_fields) in
        # crates/rill-pm-adapter/src/lib.rs v1.2.0: a valid outcome carries ONLY
        # the outcomeRequest fields (no observe-only metadata).
        outcome={ 'contract':'pm-rill-shadow','protocolVersion':1,'requestId':'o1','op':'outcome','validated':True,'actionId':'nic.ring.floor','decisionId':'d1','goal':'balanced','modelGeneration':1,
                  'sessionId':'s1','reward':0.25,
                  'contextKey':'ctx-v1:profile=p;cap=c;topo=1;path=path:lan-to-wan;route=r;workload=plain_forwarding;integ=f;goal=balanced' }
        self.assertTrue(v.is_valid(outcome))
        for field in ['validated','contextKey','reward','actionId','sessionId','decisionId','goal','modelGeneration','requestId']:
            with self.subTest(field=field):
                broken=dict(outcome); del broken[field]
                self.assertFalse(v.is_valid(broken),f'outcome must reject missing {field}')
        invalid_context=dict(outcome); invalid_context['contextKey']='v1:prefix'
        self.assertFalse(v.is_valid(invalid_context))
        # deny_unknown_fields: a foreign field is REJECTED, never ignored.
        unknown=dict(outcome); unknown['deviceProfile']='p'
        self.assertFalse(v.is_valid(unknown))
    def test_rill_ipc_observe_requires_full_metadata(self):
        sch=json.loads((ROOT/'contracts/rill-ipc.schema.json').read_text())
        v=jsonschema.Draft202012Validator(sch)
        observe=json.loads((ROOT/'schemas/rill-ipc.example.json').read_text())
        self.assertTrue(v.is_valid(observe))
        for field in ['deviceProfile','capabilityHash','topologyGeneration','pathId','routeIdentity',
                      'workloadClass','measurementClass','context','integrations','goal','integrationFingerprint',
                      'contextKey','availableActions']:
            with self.subTest(field=field):
                broken=dict(observe); del broken[field]
                self.assertFalse(v.is_valid(broken),f'observe must reject missing {field}')
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
