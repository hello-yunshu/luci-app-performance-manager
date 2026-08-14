// Verify rtnl.listener string group names (indexed loop; literal + variable).
import * as rtnl from 'rtnl';
let names = [ 'route', 'link', 'addr', 'neigh' ];
let i = 0;
for (; i < length(names); i++) {
    let name = names[i];
    let l = null;
    try {
        l = rtnl.listener(function(msg) { }, [ name ]);
    } catch (e) {
        print("VAR[" + name + "]: EXC " + e + "\n");
        continue;
    }
    print("VAR[" + name + "]: " + (l ? "ok" : "fail") + "\n");
    if (l) l.close();
}
// literal reference case (matches uc-rtnl-groups.uc try[0])
let l2 = null;
try {
    l2 = rtnl.listener(function(msg) { }, [ "route" ]);
    print("LIT[route]: " + (l2 ? "ok" : "fail") + "\n");
    if (l2) l2.close();
} catch (e) {
    print("LIT[route]: EXC " + e + "\n");
}
// no-groups default
try {
    let l3 = rtnl.listener(function(msg) { });
    print("DEFAULT: " + (l3 ? "ok" : "fail") + "\n");
    if (l3) l3.close();
} catch (e) {
    print("DEFAULT: EXC " + e + "\n");
}
