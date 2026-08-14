// t1: regex literal with quantifiers
let t1 = match("a:b", /^[0-9a-fA-F]{4}:[0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7]$/);
// t2: template literal
let t2 = `nic:pci:${"1"}`;
// t3: nullish coalescing
let t3 = null ?? 'x';
// t4: empty object literal property
let t4 = { schemaVersion: 1, stableId: null, kind: 'netdev', logicalRole: null, selector: {}, runtimeName: 'x', driver: null, evidence: [] };
// t5: for-in with let
for (let p in [1, 2, 3]) { push([], p); }
// t6: object property trailing comma
let t6 = { a: 1, b: 2, };
// t7: arrow function
let t7 = (a) => { return a + 1; };
