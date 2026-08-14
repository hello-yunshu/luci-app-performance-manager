# Rill Shadow Learning Model — 1.0.0-rc.2

Rill runs as a dedicated unprivileged service over a bounded Unix-domain socket. The root Core is the only accepted peer (`SO_PEERCRED`). Rill cannot execute commands, write UCI/sysctl/firewall state or call the Action actuator.

The Shadow engine tracks capability/topology/path/route drift, reconstructs validated outcome statistics after restart, applies measurement-quality weights (`controlled_ab` > `passive_before_after` > `health_only`), and exposes advisory output only after a minimum sample count and positive mean reward.

Persistent state lives in `/etc/performance-manager/rill`, is included in sysupgrade keep rules, and is bounded by line/file limits. Ordinary stable observations remain in memory. The service reports a logical persistent-write counter so the target soak gate can measure write amplification instead of guessing from static source.

The protocol rejects unauthorized peers, oversized/timeout/invalid UTF-8 messages, duplicate critical fields, unsupported schema/API versions and unvalidated outcomes. JSON string parsing handles UTF-8 and valid JSON escapes/surrogate pairs; malformed escapes are rejected.

A Rill recommendation carries `authority: none`. Core exposes it under `learnedAdvisory`; it is never merged into the direct apply allowlist.
