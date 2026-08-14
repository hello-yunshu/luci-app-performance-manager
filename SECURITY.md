# Security Policy

Performance Manager changes network-critical state and treats every write as privileged.

## Boundaries

- Core runs as root because OpenWrt network tuning requires it, but exposes fixed ubus methods and allowlisted Actions only.
- LuCI reaches Core through explicit rpcd ACL methods; it cannot pass arbitrary commands.
- Core process execution uses argv arrays; no dynamic `sh -c` actuation path is part of the product.
- Rill runs under a dedicated account over a bounded Unix-domain socket and accepts only the root Core peer using peer credentials.
- Rill cannot write UCI, `/proc/sys`, firewall state, execute commands or apply Actions. Its recommendations carry no authority.
- Companion is an explicit endpoint benchmark utility. It can launch bounded iperf3 only when invoked by a user; it cannot mutate router state.
- Direct apply is limited to the safe allowlist. Benchmark-class tuning is not silently converted into a direct write.
- Transactions snapshot state, lock resources, verify read-back and baseline-relative health, and verify restoration during rollback.
- Persistent history is bounded and ordinary telemetry/topology events stay in tmpfs.

## Controlled benchmark trust

A `pm-companion/v2` envelope proves only what the endpoint measured. It is not, by itself, proof that the router applied exactly one intended Action or that topology/route identity stayed unchanged. Core-side transaction and context validation remain mandatory before any outcome can be a learning label.

## Reporting

Use the Git hosting provider's private security-reporting mechanism when available. Include OpenWrt version/target, package versions, reproduction steps, affected Action/TargetRef and whether the issue can alter network/firewall state.
