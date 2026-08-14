// Determine which string group names rtnl.listener accepts (one listener per
// process because the earlier multi-group test crashed the process).
import * as rtnl from 'rtnl';
let names = [ 'route', 'link', 'addr', 'neigh', 'newroute', 'delroute', 'newlink', 'dellink', 'route+link', 'route,link' ];
for (let i in names) {
    let name = names[i];
    let l = null;
    try {
        l = rtnl.listener(function(msg) { }, [ name ]);
    } catch (e) {
        print("GRP[" + name + "]: EXC " + e + "\n");
        continue;
    }
    print("GRP[" + name + "]: " + (l ? "ok" : "fail") + "\n");
    if (l) l.close();
}
