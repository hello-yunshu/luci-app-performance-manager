// Inspect rtnl.const namespace and listener group semantics
import * as rtnl from 'rtnl';
let ckeys = [];
for (let k in rtnl.const) push(ckeys, k);
print("rtnl.const count: " + length(ckeys) + "\n");
for (let k in ckeys) print("  const." + ckeys[k] + "=" + rtnl.const[ckeys[k]] + "\n");
print("NEWROUTE=" + rtnl.const.NEWROUTE + " DELROUTE=" + rtnl.const.DELROUTE + " NEWLINK=" + rtnl.const.NEWLINK + " DELLINK=" + rtnl.const.DELLINK + "\n");
let l2 = rtnl.listener(function(msg) { print("cb2\n"); }, [ rtnl.const.NEWROUTE, rtnl.const.DELROUTE ]);
print("listener(const.NEWROUTE): " + (l2 ? "ok" : "fail") + "\n");
