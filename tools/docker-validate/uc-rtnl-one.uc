// Test rtnl.listener group sets, one group set per process via argv
import * as rtnl from 'rtnl';
import { argv } from 'fs';
let g = argv.length > 1 ? split(argv[1], ',') : [ 'route' ];
let l = null;
try {
    l = rtnl.listener(function(msg) { }, g);
    print("OK groups=" + argv[1] + "\n");
    l.close();
} catch (e) {
    print("EXC groups=" + argv[1] + " : " + e + "\n");
}
