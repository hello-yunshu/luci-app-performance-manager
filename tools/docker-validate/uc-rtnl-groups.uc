// Test rtnl.listener with string group names (no join)
import * as rtnl from 'rtnl';
let tries = [
    [ "route" ],
    [ "newroute", "delroute", "newlink", "dellink" ],
];
for (let t in tries) {
    let g = tries[t];
    let l = null;
    try {
        l = rtnl.listener(function(msg) { }, g);
    } catch (e) {
        print("try[" + t + "]: EXC " + e + "\n");
        continue;
    }
    print("try[" + t + "]: " + (l ? "ok" : "fail") + "\n");
    if (l) l.close();
}