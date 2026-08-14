# SWrt Migration

Follow the frozen three-stage plan:

1. **A — detect-only:** install PM, compare native Packet Steering, ring state and existing BBR/fast-path ownership. Do not remove existing overlay.
2. **B — PM ownership for narrow safe scope:** migrate Hyper-V ring intent to TargetRef + `pm_policy_replay`; keep native Packet Steering observe/respect. Existing BBR/CC remains preexisting/external.
3. **C — deduplicate only after evidence:** after reboot/hotplug/rollback verification, remove only the duplicate SWrt ring overlay. Never delete unrelated acceleration/CC configuration merely because PM can observe it.
