# luci-app-performance-manager

[English](README.en.md) | **中文**

<p align="center">
  <img src="logo.png" alt="OpenWrt Performance Manager" width="480">
</p>

<p align="center">
  <strong>面向 OpenWrt 的 Capability-first、Topology-aware、Transactional 性能控制平面</strong>
</p>

<p align="center">
  先发现 OpenWrt / 驱动 / 平台已经具备的能力，再解析 Topology / TargetRef / Path / Workload，经过 Policy、Compatibility、Locks 与 Health Guard 检查后形成合法 Action，并通过事务、read-back、健康验证与回滚闭环执行。它不是 sysctl 参数大全，也不会在 OpenWrt 已有成熟实现时替换原生 provider。
</p>

---

## 功能特性

- **能力优先**：稳定 TargetRef，避免长期策略绑定 `eth0`；PPPoE / VPN 场景优先解析真实 underlay
- **Topology 感知**：基于路由 / 策略路由证据与 rtnl 事件维护 topology、path 与 workload 模型
- **原生 Packet Steering**：发现 / 观察 / 尊重 OpenWrt 原生实现，不重写算法
- **NIC offload 保护**：observe / protect，兼容 OpenClash / PassWall / HomeProxy / SQM / qosify / mwan3 / pbr / VPN / Docker 发现
- **Hyper-V 安全策略**：`hv_netvsc` 1024 ring floor 保守策略，支持 boot / device / topology replay
- **Telemetry + Health Guard**：evidence/confidence Analyzer、baseline-relative 健康门禁、资源锁、持久 pending marker、verified rollback 与真实 monotonic commit-confirm 引擎
- **Phase-7 Benchmark 编排**：irqbalance、backlog/budget、buffers、busy poll、tx queue、coalescing、CC、qdisc、SFO/HFO/SFE、CPU governor；只有存在精确可逆契约时才执行 provider
- **受控 A/B 真值**：持久 control evidence → 单变量事务 candidate → candidate evidence → 验证后回滚 → 结果持久化 → 可选 Rill outcome；缺失 / 无效 evidence 永远不会变成 `validated=true`
- **Rill Runtime v3 Smart Decision**：源码与 canonical package 由外部 Rill feed 拥有；统一 PM 包依赖共享的 `rill-runtime`，自身不含 Runtime 二进制，Core 统一执行 Conservative/Assisted selector，保留安全 allowlist、NO_OP、置信度、漂移和冷却门禁。
- **Assisted Auto**：默认关闭，必须显式选择 + 维护窗口 + 低流量门禁 + 安全 allowlist
- **多平台指导**：Generic x86、Hyper-V、KVM（含 Proxmox VE guest 建议）
- **Companion Agent**：显式 LAN/WAN iperf3 端点工具，不拥有路由器修改权限
- **LuCI Supported-first UI**：简体中文界面

## 安全不变量

- Core 不硬依赖 LuCI / rpcd / Rill，可独立运行
- Rill 仅接受 root Core 通过有界 stdin/stdout subprocess 连接，不能执行命令，不能写 UCI / sysctl / firewall
- 直接 Apply 只使用固定安全 Action allowlist；benchmark 类 action 不会被静默提升为直接写入
- 已有用户 / 外部 / 先前状态优先；卸载只恢复 PM 当前拥有的运行时 lease，绝不覆盖实时漂移做 stale 回滚
- 事务验证 read-back 与 baseline-relative 健康；恢复失败记为失败而非成功回滚
- 普通 telemetry / topology 刷新留在 tmpfs；持久历史有界
- 被动 / 健康类 benchmark 观察保持 `validated=false`；只有真实 validated outcome 才更新 Rill 学习
- Smart History 以 `candidateId`（business action + stable target + evaluation path）隔离；旧的无法安全映射到 target/path 的 action history 会被丢弃，不会复制到多个候选

## 安装

先按设备版本和架构配置[统一软件源](https://github.com/hello-yunshu/yun-openwrt-packages/blob/main/docs/INSTALL.md)，然后安装 `luci-app-performance-manager-all`。

```sh
# OpenWrt 24.10.8
opkg install luci-app-performance-manager-all

# OpenWrt 25.12.6
apk add luci-app-performance-manager-all
```

也可以从 [GitHub Releases](https://github.com/hello-yunshu/luci-app-performance-manager/releases) 下载匹配设备版本和架构的 IPK 或 APK。两种安装方式都需要配置统一软件源，以便解析 `rill-runtime` 和 `rill-runtime-manager`。PM 单包包含 Core、LuCI 和 Rill 集成。其他插件可共用软件源提供的 Runtime。

已经安装同名单包的设备，可以通过软件源直接升级。

### 从旧拆分包或 Preview 迁移

如果设备装的是旧拆分包（`performance-manager`、`luci-app-performance-manager`、`performance-manager-rill`、`luci-i18n-performance-manager-zh-cn`），先备份 `/etc/config/performance-manager` 和 `/etc/performance-manager/`，在维护窗口移除已安装的旧 PM 包，再安装统一包。

如果设备有 `rill-runtime-preview`，先确认其他插件已迁移到 Stable Runtime。在维护窗口备份 PM 配置和数据，移除旧 PM 包及 Preview 后，再安装统一包。包管理器报告还有依赖时，先处理依赖它的插件。共享 Stable 包 `rill-runtime` 可以留在设备上。

### 包信息

| 项目 | 值 |
|---|---|
| 推荐包名 | `luci-app-performance-manager-all`（单一 PM 包） |
| 目标 | OpenWrt 24.10.8 IPK / 25.12.6 APK；以 CI 和发布资产逐项验证为准 |
| 当前源码候选 | `1.1.2` |
| 统一 PM 包版本 | `1.1.2-r1` |
| 服务脚本 | `/etc/init.d/performance-manager` |
| UCI 配置 | `/etc/config/performance-manager` |
| 核心程序 | `/usr/sbin/performance-manager.uc` |
| RPC 后端 | `performance-manager`（`ubus call performance-manager <method>`） |

### 依赖

```text
ucode ucode-mod-fs ucode-mod-ubus ucode-mod-uci ucode-mod-rtnl ucode-mod-uloop ucode-mod-log ucode-mod-socket uci ubus coreutils-timeout rpcd luci-base luci-i18n-base-zh-cn
```

统一包会自动解析以上 Core / LuCI 运行依赖，并额外依赖共享的 `rill-runtime-manager` 与 `rill-runtime`。`recommended` 性能 profile 中的 `ethtool`、`ip-full`、`tc-tiny`、`ss`、`nstat` 等属于可选诊断工具，不影响 PM 核心启动；缺失时 profile 会报告不完整。

## 使用指南

### LuCI 界面（网络 → Performance Manager）

界面默认以简体中文呈现，并跟随 OpenWrt/LuCI 的系统语言设置自动切换：在 LuCI「系统 → 语言和界面」中选择中文即显示中文，选择英文即显示英文（英文为次要语言，作为未匹配语言时的回退）。

| 页面 | 说明 |
|---|---|
| Overview | 运行状态、健康、最近事务概览 |
| Smart Optimization | 推荐动作与安全应用 |
| Performance Test | Phase-7 受控 benchmark 编排 |
| Capabilities | 能力 / Topology / TargetRef 视图 |
| Rill Intelligence | Runtime v3 学习、排序与决策台账 |
| History & Rollback | 历史与回滚 |
| Settings / Advanced | 配置项 |

### Runtime API

```sh
ubus call performance-manager status '{}'
ubus call performance-manager capabilities '{}'
ubus call performance-manager topology '{}'
ubus call performance-manager targets '{}'
ubus call performance-manager paths '{}'
ubus call performance-manager analyze '{}'
ubus call performance-manager recommendations '{}'
ubus call performance-manager transactions '{}'
ubus call performance-manager locks '{}'
ubus call performance-manager history '{"limit":100}'
ubus call performance-manager diagnostics '{}'
ubus call performance-manager rill_status '{}'
```

合法安全动作通过 Action ID + 解析后的 TargetRef 应用：

```sh
ubus call performance-manager apply '{"actionId":"nic.ring.floor","target":"<stableId>"}'
ubus call performance-manager confirm '{"transactionId":"<tx>"}'
ubus call performance-manager rollback '{"transactionId":"<tx>"}'
```

Benchmark 生命周期：

```sh
ubus call performance-manager benchmark_start '{"actionId":"<actionId>","measurementClass":"controlled_ab"}'
ubus call performance-manager benchmark_status '{"sessionId":"<session>"}'
ubus call performance-manager benchmark_stop '{"sessionId":"<session>"}'
```

## 项目结构

```text
package/performance-manager/files/
├── etc/
│   ├── config/performance-manager    # UCI 配置
│   ├── init.d/performance-manager    # procd 服务脚本
│   └── uci-defaults/90-performance-manager
├── lib/upgrade/keep.d/performance-manager
└── usr/
    ├── sbin/performance-manager.uc   # Core（ucode/ubus）
    └── share/performance-manager/
        ├── contracts.uc              # 安全动作契约
        ├── profiles/                 # 能力 profile
        └── schemas/                  # JSON schema（校验）

package/luci-app-performance-manager/
├── htdocs/luci-static/resources/performance-manager/   # api.js / ui.js
├── htdocs/luci-static/resources/view/performance-manager/  # 8 个视图
├── po/zh_Hans/                        # 简体中文翻译
└── root/usr/share/luci/menu.d/        # LuCI 菜单注册

package/luci-app-performance-manager-all/Makefile  # 将 PM 自有内容及编译后的 zh-cn LMO 汇入单一目标包
```

## 架构设计

```text
┌──────────────┐ ubus/rpcd ┌────────────────────────┐
│  LuCI 前端   │ ─────────→ │  performance-manager   │
│ (8 个视图)   │ ←───────── │  Core (ucode/ubus)     │
└──────────────┘  JSON     └───────────┬────────────┘
                                      │ stdin/stdout subprocess（有界，Runtime v3）
                          ┌───────────▼────────────┐
                          │ performance-manager-rill │
                          │ (external Runtime glue) │
                          └───────────┬────────────┘
                                      │ generic Runtime v3 / stdin/stdout
                          ┌───────────▼────────────┐
                          │ shared Runtime package │
                          │ ranking, no actuator    │
                          └────────────────────────┘
```

> **所有权边界。** Rill Runtime 源码与 canonical package 由 `hello-yunshu/rill-openwrt-packages` 拥有；PM、CFI 等消费者依赖同一个已资格验证的 Stable provider，由它唯一拥有 `/usr/bin/rill-runtime`。Runtime v3 只返回排序/反馈结果，没有设备执行权；缺失、不兼容或状态恢复失败时 fail-closed。

## MacBook + Docker 本地 Portable 验证

在 push 前，可以在 MacBook 上执行可重复的 Repository Software Portable 验证：

```sh
make portable-macos
# 或：tools/docker-validate/run-local-macos.sh
```

前置条件：Docker Desktop、Git、Python 3、已认证的 `gh` CLI，以及可访问 GitHub / OpenWrt 的网络；当前 commit 对应的 same-SHA CI 和 same-SHA Build 必须已经成功完成。首次运行会自动下载并校验 OpenWrt 25.12.6 x86_64 rootfs；后续运行可复用 rootfs cache，但每次都会重新校验官方 `sha256sums`。同 SHA Build 尚未完成时结果是 `BLOCKED`，不是项目代码 `FAIL`。

入口会复用仓库现有的 source audit、OpenWrt ucode harness、artifact identity、package-composition gate 和 portable gate。所有运行证据写入未跟踪的 `local-evidence/`，并绑定当前 commit SHA；构建包必须来自同一 SHA 的 GitHub Actions Build，不能使用 latest 或旧分支缓存。

`Mac Docker PASS != Hardware PASS`。自 2026-11-22 起，仓库所有者取消了「硬件证据是 Stable 前置要求」的策略：`portable-docker` 档位全部 gate PASS 即可授权 Stable。但 portable 证据仍如实记录 `hardwareCoverage = NOT_EVALUATED`，release notes 会明示未覆盖 real NIC、Hyper-V/KVM、LAN-WAN、sysupgrade、reboot 和真实路由器 12h soak。Docker Desktop 不可用、linux/amd64 仿真不可用、网络下载失败或 same-SHA artifact 未准备好时，入口会输出可诊断的 `BLOCKED`，不会伪造 PASS。

**数据流**：

1. Core 通过 ubus / rtnl / uci 发现能力与 topology，维护稳定 TargetRef
2. 前端通过 `ubus call performance-manager <method>` 查询状态 / 能力 / 建议
3. 合法动作通过事务引擎执行：read-back → 健康验证 → commit-confirm → 必要时回滚
4. validated outcome 可选写入 Rill，Rill 仅返回 advisory；Rill 缺失 / 协议不兼容时 Core 保持正常并 fail-closed
5. Auto 统一经过 Smart Action Selector：Rill 只有在 ready、样本数/置信度/漂移/冷却/合法性均通过时才能影响安全动作；`pm.noop` 始终可用且永不执行变更

## UCI 配置参考

### core section（main）

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enabled` | boolean | 1 | 启用 Core |
| `automation` | enum | conservative | 自动化级别 |
| `assisted_auto` | boolean | 0 | 显式开启 Assisted Auto（二次确认） |
| `maintenance_start` / `maintenance_end` | string | 03:00 / 05:00 | 维护窗口 |
| `goal` | enum | balanced | 优化目标 |
| `profile` | string | recommended | 能力 profile |
| `telemetry` / `history` | boolean | 1 | 采集与持久历史开关 |
| `telemetry_interval` / `deep_interval` | integer | 45 / 600 | 采样间隔（秒） |
| `commit_confirm_seconds` | integer | 30 | commit-confirm 确认窗口 |
| `state_dir` | string | /tmp/performance-manager | 运行时状态（tmpfs） |
| `persistent_dir` | string | /etc/performance-manager | 持久目录 |
| `health_dns_name` | string | openwrt.org | 健康检查 DNS 目标 |
| `oom_window_seconds` / `max_load_per_cpu` / `max_cpu_steal_percent` / `max_thermal_millicelsius` | integer | 600 / 2 / 20 / 90000 | 健康门禁阈值 |

### rill section（Runtime v3）

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `enabled` | boolean | 1 | 启用外部 Runtime |
| `mode` | 固定语义 | advisory | Runtime 只返回 advisory，无 Apply 权限；旧 `shadow` section 仅在升级迁移时读取一次 |
| `binary` | string | (空) | 外部 Runtime 路径；空值使用 `/usr/bin/rill-runtime`，缺失或不兼容时集成 fail-closed / 阻塞 |
| `max_message` | integer | 65536 | 最大消息字节 |
| `timeout_ms` | integer | 1000 | 调用超时 |
| `state_dir` | string | /etc/performance-manager/rill | Rill 持久状态 |

Smart Decision 默认使用 8 个已验证样本进入 `ready`，Conservative/Assisted 的最低置信度分别为 0.65/0.75；性能分布漂移阈值为 0.20，漂移恢复需要 3 个新样本，动作冷却默认 600 秒。

### benchmark section

| 选项 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `require_explicit_start` | boolean | 1 | 必须显式启动 benchmark |
| `one_variable` | boolean | 1 | 单变量受控 A/B |
| `allow_background_saturation` | boolean | 0 | 不允许后台压满 WAN |
| `default_measurement_class` | enum | passive_before_after | 默认测量类别 |
| `candidate_timeout_seconds` | integer | 120 | candidate 超时 |
| `session_idle_seconds` | integer | 600 | 会话空闲超时 |

## 构建与审计

本项目使用 GitHub Actions 自动构建与验证，推送 main 分支或手动触发即可运行：

**`ci.yml`（源码、行为、契约与 Runtime v3 验证）**
- **static**：单测 + 契约校验 + source gates + final audit + LuCI JS 语法 & render smoke
- **rill-runtime-v3**：构建精确 Runtime 提交，执行真实 handshake/health/observe/decide/feedback、失败闭合、重复反馈和分区持久化检查
- **openwrt-ucode**：官方 OpenWrt 25.12.6 rootfs 中编译校验 Core ucode

**`build-openwrt.yml`（远程官方 SDK 构建）**
- **openwrt-sdk-build**：为 OpenWrt 24.10.8/IPK 与 25.12.6/APK 的六个架构构建统一 PM 包和 Core。旧 LuCI 和 Rill 拆分包只在 x86_64 APK 目标构建，供迁移和包组合门禁使用。

Public release staging 只输出 12 个目标专属 unified PM IPK/APK 与 `SHA256SUMS.txt`；JSON、MD、ZIP、split packages 和 standalone Runtime 全部留在 Actions artifacts。

> Runtime v3 的主机子进程 job 证明通用 Runtime 行为；PM Core-to-Runtime 的 OpenWrt 生产 roundtrip 仍是独立门禁，未完成时证据保持 `NOT_EVALUATED`/`BLOCKED`，不会被脚本升级成 PASS。

### 使用 OpenWrt SDK 从源码构建

先在 SDK 中配置提供 `rill-runtime` 和 `rill-runtime-manager` 的 Rill 源码 feed。常规构建只需指定统一包。

```sh
cd /path/to/openwrt-sdk
./scripts/feeds update -a
./scripts/feeds install -a
mkdir -p package/openwrt-performance-manager
cp -a /path/to/luci-app-performance-manager/package/* package/openwrt-performance-manager/
cp /path/to/luci-app-performance-manager/VERSION package/openwrt-performance-manager/
make defconfig
make package/luci-app-performance-manager-all/compile V=s
```

只验证 Core 时，使用 `make package/performance-manager/compile V=s`。

本地快速验证：

```sh
make audit          # 单测 + 契约校验 + source gates + final audit
make package        # 生成发布包
```

- 目标机门禁：`scripts/openwrt-target-gate.sh`
- 资源 / 写入 soak：`scripts/openwrt-resource-soak.sh`
- 外部验证证据：`docs/EXTERNAL_VALIDATION.md`

> 历史公开 `1.0.3` 的 portable-docker profile 不宣称 Hyper-V、真实路由器 A/B、firmware sysupgrade 或 24 小时 soak 覆盖；这些仍需单独的 `hardware` profile 证据。当前 `1.0.4` 及以后 Stable 只接受所有 hardware gates 为 PASS 的证据；Runtime qualification 是独立的发布门禁。

## 文档

- `docs/ARCHITECTURE.md` · `docs/IMPLEMENTATION_STATUS.md` · `docs/RELEASE_CHECKLIST.md`
- `docs/EXTERNAL_VALIDATION.md`

## 许可证

本项目采用 **GNU GPL v3.0-only**（[LICENSE](LICENSE)）。作为自由软件，你可以自由使用、修改与分发，但任何修改版本也必须以 GPL-3.0 许可发布并提供对应的源代码。
