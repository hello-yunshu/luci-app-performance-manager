// Definitive: numeric command IDs (RTM_*) + numeric multicast groups (RTNLGRP_*).
// RTM_NEWLINK=16 RTM_DELLINK=17 RTM_NEWROUTE=24 RTM_DELROUTE=25
// RTNLGRP_LINK=1 RTNLGRP_IPV4_ROUTE=7 RTNLGRP_IPV6_ROUTE=11
// NOTE: do NOT call .close() in this container build (known segfault bug).
import * as rtnl from 'rtnl';
print("TOP RTM_NEWROUTE=" + rtnl.RTM_NEWROUTE + " const RTM_NEWROUTE=" + rtnl.const.RTM_NEWROUTE + "\n");
let l = null;
try {
    l = rtnl.listener(function(msg) { }, [ 16, 17, 24, 25 ], [ 1, 7, 11 ]);
    print("NUMERIC[16,17,24,25]/[1,7,11]: " + (l ? "ok" : "fail") + "\n");
} catch (e) {
    print("NUMERIC: EXC " + e + "\n");
}
// default groups variant (all commands, default group = RTNLGRP_LINK)
try {
    let l2 = rtnl.listener(function(msg) { });
    print("DEFAULT-ALLCMDS: " + (l2 ? "ok" : "fail") + "\n");
} catch (e) {
    print("DEFAULT-ALLCMDS: EXC " + e + "\n");
}
print("DONE\n");
