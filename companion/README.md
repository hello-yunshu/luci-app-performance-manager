# Performance Manager Companion Agent

Phase 12 companion endpoint for **explicit** benchmark work. It is intentionally not a router controller.

- `capabilities`: report endpoint capabilities.
- `server`: run a one-shot `iperf3` WAN-side server.
- `client`: run a bounded `iperf3` LAN-side client and save JSON evidence.
- `compare`: compare a control and candidate result and emit a `pm-companion/v2` evidence envelope.

It never writes UCI, sysctl, firewall or OpenWrt state. It never uses `shell=True`. A companion evidence envelope validates only the endpoint measurement; Performance Manager Core must separately validate the current TargetRef/topology/route, transaction and rollback before the evidence can become a Rill learning outcome.
