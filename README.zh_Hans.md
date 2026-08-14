# OpenWrt Performance Manager

> 面向 OpenWrt 的 Capability-first、Topology-aware、Transactional 性能控制平面。

**首要目标：** OpenWrt 25.12.x / x86_64
**当前源码候选：** `1.0.0-rc.2`
**默认安全策略：** Conservative；不静默压满 WAN；Rill 永远没有直接 Apply 权限。

本项目不做“参数大全”。它先发现 OpenWrt/驱动/平台已经具备的能力，再解析 Topology / TargetRef / Path / Workload，经过 Policy、Compatibility、Locks 和 Health Guard 后才形成合法 Action，并通过事务、read-back、健康验证和回滚闭环执行。

## 已实现

- 稳定 TargetRef，避免长期策略绑定 `eth0`；PPPoE/VPN 场景优先解析真实 underlay。
- OpenWrt 原生 Packet Steering：发现 / 观察 / 尊重，不重写原生算法。
- Hyper-V `hv_netvsc` 1024 ring floor 安全策略及 boot/device/topology replay。
- NIC offload observe/protect、OpenClash/Passwall/HomeProxy/SQM/qosify/mwan3/pbr/VPN/Docker 兼容发现。
- Telemetry、evidence/confidence Analyzer、baseline-relative Health Guard、资源锁、持久 pending marker、verified rollback、真实 monotonic commit-confirm 引擎。
- Phase-7 Benchmark 已形成真实受控编排：control evidence → 单变量事务 candidate → candidate evidence → 先回滚并验证 → 再比较/落盘/Rill；无法证明精确可逆的 provider 会明确 capability-block。
- Rill Shadow Learning：drift、validated outcome 加权 bandit、Decision Ledger、model health；只输出 advisory。
- Assisted Auto：默认关闭，必须显式选择 assisted + 打开开关 + 维护窗口 + 低流量，且仍只允许 safe allowlist。
- Generic x86 / Hyper-V / KVM（含 Proxmox VE guest 兼容建议）。
- Companion Agent：显式 LAN/WAN iperf3 端点工具，不拥有路由器修改权限。
- LuCI Supported-first UI 与简体中文翻译。

## 三个 OpenWrt 包

- `performance-manager`：独立 Core。
- `luci-app-performance-manager`：LuCI UI。
- `performance-manager-rill`：独立低权限 Rill Shadow sidecar。

## 本地审计

```sh
make audit
make package
```

详细状态见 `docs/IMPLEMENTATION_STATUS.md`；稳定版门禁见 `docs/RELEASE_CHECKLIST.md`。目标机可直接运行 `scripts/openwrt-target-gate.sh`；sysupgrade 前后分别运行 `scripts/openwrt-sysupgrade-gate.sh prepare` / `verify`；24h 资源/写入门禁运行 `scripts/openwrt-resource-soak.sh`。当前严格标记为 `1.0.0-rc.2`，因为真实 OpenWrt x86_64 SDK 构建、VM 启动、Hyper-V/KVM hotplug/rollback、sysupgrade、24h+ soak 和 LAN→Router→WAN controlled A/B 不能用静态测试冒充。
