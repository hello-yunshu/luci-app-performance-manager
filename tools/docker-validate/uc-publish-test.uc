// Test: publish with bare function method vs { call: fn } object method
import * as ubus from 'ubus';
let conn = ubus.connect();
if (!conn) { print("no-conn\n"); exit(1); }
let obj = conn.publish("pm.test.bare", {
    status: function(req, msg) { req.reply({ ok: true }); }
});
print("bare: " + (obj ? "ok" : "fail") + "\n");
let obj2 = conn.publish("pm.test.obj", {
    status: { call: function(req, msg) { req.reply({ ok: true }); } }
});
print("objcall: " + (obj2 ? "ok" : "fail") + "\n");
