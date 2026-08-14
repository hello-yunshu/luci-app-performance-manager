// Diagnose rtnl module API (no join)
import * as rtnl from 'rtnl';
let keys = [];
for (let k in rtnl) push(keys, k);
print("rtnl key count: " + length(keys) + "\n");
for (let k in keys) print("  " + k + "=" + keys[k] + "\n");
print("RTM_NEWROUTE=" + rtnl.RTM_NEWROUTE + "\n");
print("RTM_DELROUTE=" + rtnl.RTM_DELROUTE + "\n");
print("RTM_NEWLINK=" + rtnl.RTM_NEWLINK + "\n");
print("RTM_DELLINK=" + rtnl.RTM_DELLINK + "\n");
let l1 = rtnl.listener(function(msg) { print("cb\n"); });
print("listener(no-groups): " + (l1 ? "ok" : "fail") + "\n");