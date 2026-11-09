# 审计问题收敛计划

- 日期：2026-11-09
- 仓库：`luci-app-performance-manager`
- 分支：`codex/runtime-owner-qualification`
- 审计基线 HEAD：`2dd4f6796b37c2665b03bb4acbcf2b64d2161a89`
- 源码候选版本：`1.0.4`
- 本轮性质：**只出计划，不修代码、不改 CI、不发版、不 push**
- 输入：2026-11-09 实际运行审计的 H1–H4、M1–M6、L1–L4，以及三个 BLOCKED 项（LuCI 页面实测、真实目标门禁/24h soak/Hardware Stable、v1.0.4 发布）

## 0. 结论：需要 5 个阶段

**判断：5 个阶段收敛。**

理由不是“问题多所以要分五段”，而是这套问题存在四个不可合并的依赖层，外加一个独立的授权边界：

1. **证据基线必须先成立**。H1 不是简单的“重新生成文档”：`scripts/final_audit.py` 在写完生成物之后才判断工作树是否脏，因此在干净检出上本地运行也会得到 `WORKTREE_UNCOMMITTED`。不先修这个身份绑定，后面所有修复都无法用“这个快照属于哪个 commit”来收尾。
2. **代码行为必须先稳定，再冻结契约/文档/证据**。M5、M6、L1 和 LuCI 实测都可能改 Core 或测试；如果先做 H2/H3 的证据冻结，紧接着的代码改动就会让 `testCount`、`coreSourceBytes` 和快照立刻过期，H1 会重新破掉。因此“本地行为与页面实测”必须排在“契约与文档对账”之前。
3. **H2 和 H3 必须同一阶段**。两者都落在 Rill 契约/最终证据链上，且共享 `contracts/rill-runtime.json`、`docs/rill-integration-status.json`、`scripts/final_audit.py`、`scripts/aggregate_final_evidence.py` 和 `IMPLEMENTATION_STATUS.md`。拆开会让同一批文件被改两遍，并留下“契约已合并但证据还没带 pin”的中间态。
4. **设备证据不能和本地证据合并**。M3 的 `diagnostics` 超时必须在真机复测才能定性；B2 的 target gate、sysupgrade 和 24h soak 本身就是设备/时间门禁。把它们塞进本地阶段，会让阶段出口被硬件可用性卡死。
5. **发布决策是独立授权边界，不能和设备阶段合并**。B3 需要发布权限；H4 的正确写法取决于“是否真的出 v1.0.4”。即使最终决定**不发布**，H4 仍然可以关闭——把 README 改成指向实际存在的 v1.0.3 资产即可。把发布和设备合并，会让“不做发布”这种合法出口无法表达。

5 个阶段已经是最小可独立闭环的层数：再少就会把“代码改动”和“证据冻结”揉在一起，或者把“设备证据”和“发布授权”揉在一起；再多则会把 H2/H3、M1/M2/M4 这些必须同批修改的条目拆成机械阶段。

## 1. 阶段依赖图

```text
阶段 1  证据基线（H1, L4）
   │
   ▼
阶段 2  本地行为与 LuCI 实测（M5, M6, L1, B1）
   │
   ▼
阶段 3  契约与文档对账（H2, H3, M1, M2, M4, L2, L3）
   │
   ▼
阶段 4  设备证据（M3, B2）
   │
   ▼
阶段 5  发布决策与最终封存（B3, H4；复验 H1/L4）
```

阶段 2 和阶段 3 在技术上都可以在阶段 1 之后启动，但本计划**强制串行**：阶段 2 的代码改动必须先落地，阶段 3 冻结的测试数、Core 字节数和证据才不会再被下一阶段改脏。阶段 4 若因 M3 修复而改代码，必须在阶段 4 内重新生成并提交审计快照；阶段 5 做最终封存。

## 2. 条目总表

| ID | 问题 | 关键证据（文件:行 / 实测） | 阶段 | 条件 |
|---|---|---|---|---|
| H1 | 提交的审计快照不是 HEAD 的：身份、测试数、Core 字节数均不匹配 | `docs/FINAL_AUDIT.json:5` 为 `WORKTREE_UNCOMMITTED`；提交版 `testCount=170`、`coreSourceBytes=304206`，实际重跑为 `181`、`304821`；根因在 `scripts/final_audit.py:30-46`（先写生成物、后判断脏树） | 1 | 本地即可 |
| L4 | 生成物污染工作树 | `git status --porcelain`：6 个 `docs/*` 被修改，`dist/` 未跟踪 | 1 | 本地即可 |
| M5 | 权限不足时错误信息误导 | `performance-manager.uc:94-98` 统一输出 `unable to connect to ubus`，非 root 运行无法区分“socket 不存在”和“权限不足” | 2 | 本地即可 |
| M6 | `benchmark_start {}` 默认启动 benchmark | `performance-manager.uc:3721` 缺省 `actionId='observe'`；空参数会创建 passive session，而不是拒绝 | 2 | 本地即可 |
| L1 | `history` 负 `limit` 被钳成 1 | `performance-manager.uc:4381`：`max(1, +(msg?.limit ?? 100))`；负值返回 1 行，语义不明确 | 2 | 本地即可 |
| B1 | LuCI 页面实测被环境阻断 | 审计实测所有 LuCI 路由 500（`left-hand side expression is null`）；内置路由同样 500；portable rootfs 的 ucode 缺 `fs.access`，升级 `ucode/libucode`、`luci-base` 后仍 500，判定为 rootfs/LuCI 版本漂移，不是 PM 专属缺陷 | 2 | 本地即可（需先对齐容器 ucode/LuCI 版本） |
| H2 | 两份 Rill contract 漂移 | `contracts/rill-runtime.json:13-28`：`dcfdb906…` / release 2 / run `38928695476`；`contracts/rill-dependency.json:29-42`：`a540a0a…` / release 1 / run `33479147529`；现有脚本只读 `rill-runtime.json`，`rill-dependency.json` 已无消费者 | 3 | 本地即可 |
| H3 | Rill pin 未进最终证据 | `docs/rill-integration-status.json` 无 `releasePinStructureVerdict`；`scripts/rill_contract_check.py:45-55` 不写该字段；`scripts/final_audit.py:192` 读出来是 `None`；`aggregate_final_evidence.py` 不携带 pin commit/release/run | 3 | 本地即可（需重跑 CI 验证产物） |
| M1 | “Actions pinned to SHAs” 不实 | `docs/IMPLEMENTATION_STATUS.md:67` 声称 SHA pin；实际 `ci.yml` 使用 `@v7`；`scripts/check_action_refs.py:10-11` 反而禁止 40 位 SHA 和 `latest/HEAD/main`，仓库策略是可读 tag | 3 | 本地即可 |
| M2 | ROADMAP 的 CI job 名过时 | `ROADMAP.md:5` 仍写 `pm-rill-provenance`、`pm-rill-runtime`、`pm-core-rill-roundtrip`、`openwrt-ucode`；实际 `ci.yml:12,46,142` 为 `static`、`rill-runtime-v3`、`production-core-rill-integration`，构建 job 为 `build-openwrt.yml:19` 的 `openwrt-sdk-build` | 3 | 本地即可 |
| M4 | TEST_PLAN 的 cargo 门禁不可执行 | `docs/TEST_PLAN.md:35` 要求 `cargo test --locked` / `cargo check --locked`；仓库无 `Cargo.toml`，Rust Runtime 不 vendored | 3 | 本地即可 |
| L2 | local-evidence 互相矛盾 | `local-evidence/LOCAL_VALIDATION.md:6-17` 为 BLOCKED（commit `99711f1`）；`local-evidence/LOCAL_VALIDATION 3.md:6-17` 为 PASS（commit `f551e6e`）；`local-evidence/docker 3/`、`local-evidence/source 3/` 为空 | 3 | 本地即可 |
| L3 | 历史 Rill provenance 仍易被当成当前 | `docs/rill-provenance.json:2-8` 仍是 `1.5.1` / `v1.5.1`；当前契约是 `1.5.6` | 3 | 本地即可 |
| M3 | `diagnostics` 默认超时 | `performance-manager.uc:4243`（实现）、`:4400`（发布）；容器实测默认 30.03s 超时 `rc=249`，`-t 120` 为 41.08s；必须真机复测定性 | 4 | 需要真机 |
| B2 | 真实目标门禁/24h soak/Hardware Stable 未评估 | `docs/RELEASE_CHECKLIST.md` 全部未勾选；`docs/FINAL_AUDIT.json:8-9` 为 `functionalIntegrationVerdict=NOT_EVALUATED`、`stableReleaseVerdict=NOT_EVALUATED` | 4 | 需要真机 |
| H4 | README 安装路径与实际 release 不符 | `README.md:91,97,108` 要求 `performance-manager-all-v<VERSION>-<arch>.apk` 且三架构；`gh release view v1.0.3` 实际只有 `luci-app-performance-manager-all-1.0.3-r1.apk`（x86_64）；新命名只在 `prerelease.yml:101` / `stable-release.yml:113` 生成，尚未执行 | 5 | 取决于 B3 是否发布；本地 + 发布权限 |
| B3 | v1.0.4 发布未执行 | 当前 `VERSION=1.0.4`，但无 v1.0.4 release；发布工作流未运行 | 5 | 需要发布权限 |

## 3. 阶段详情

### 阶段 1：证据基线（H1, L4）

**目标**：让仓库里提交的审计快照可证明地属于当前 HEAD，并且可在干净工作树上重复生成。

**包含条目**：H1、L4。

**前置/依赖**：无；这是所有后续阶段的前置。

**为什么不能只重跑 `make audit`**：
`scripts/final_audit.py` 先执行 `step()`，这些步骤会改写 `docs/HOST_SYNTAX_REPORT.json` 等受控文件；随后 `git_commit()` 才执行 `git status --porcelain --untracked-files=no`。因此在本地干净检出上，生成过程本身就会让工作树变脏，函数返回 `WORKTREE_UNCOMMITTED`。必须在生成前捕获 HEAD，或显式排除已知生成物路径；不能靠“再跑一次”解决。

**出口条件（全部可判定）**：

1. `git rev-parse HEAD` 与已提交 `docs/FINAL_AUDIT.json` 的 `.pmCommitSha` 完全相等，且不是 `WORKTREE_UNCOMMITTED`。
2. 已提交快照的 `.localEvidence.unitAndContractTests.count` 等于 `python -m unittest discover -s tests` 的真实 `Ran N tests`；`.packages["performance-manager"].bytes` 等于 Core 文件真实字节数。
3. 在干净工作树上执行 `make audit` 后 `git diff --exit-code` 为 0（生成幂等）；若生成器仍写入不同内容，阶段不通过。
4. `git status --porcelain` 为空；`dist/` 不出现在仓库工作树中（归档到仓库外，或在获得确认后加入 `.gitignore`）。
5. 有回归测试或自检覆盖“生成器在干净树 + 生成物已存在时仍输出 HEAD，而不是 `WORKTREE_UNCOMMITTED`”。

**条件**：本地即可。

**预计改动文件**：
- `scripts/final_audit.py`（HEAD 捕获顺序 / 生成物路径排除 / 可选 `--commit-sha`）
- `tests/`（新增或扩展审计身份测试）
- `docs/FINAL_AUDIT.json`、`docs/FINAL_AUDIT.md`、`docs/source-audit.json`、`docs/HOST_SYNTAX_REPORT.json`、`docs/RESOURCE_BUDGET.json`、`docs/rill-integration-status.json`（重新生成）
- `.gitignore`（仅在确认后处理 `dist/`）

**回退方式**：
- 生成器改动和快照提交分开提交；若快照异常，`git revert` 快照提交，保留生成器修复，重新生成。
- 不 amend 历史提交；不强制覆盖旧快照。
- `dist/` 在删除前先归档到仓库外；未获确认不删除。

**本轮特别说明**：当前 6 个被 `make audit` 修改的 `docs/*` 和未跟踪的 `dist/` **原样保留，不丢弃**。本计划执行到阶段 1 时再重新生成并提交；阶段 5 最终封存时必须再次在干净工作树生成。

---

### 阶段 2：本地行为与 LuCI 实测（M5, M6, L1, B1）

**目标**：先把会在本地改变 Core 行为和页面证据的问题收敛，避免后续证据冻结被代码改动打穿。

**包含条目**：M5、M6、L1、B1。

**前置/依赖**：阶段 1 完成；否则阶段 2 的代码改动没有可归属的基线。

**出口条件（全部可判定）**：

1. **M5**：以非 root 用户启动 Core 时，输出能明确区分 `ubus-permission-denied` 与 `ubus-socket-unavailable`（至少包含 socket 路径、存在性、权限/属主和当前 euid）；以 root 启动的 smoke 仍 PASS；新增测试断言两种错误文本。
2. **M6**：`ubus call performance-manager benchmark_start '{}'` 返回 `benchmark-action-required`，且不产生新的 benchmark session 文件；显式传 `{"actionId":"observe"}` 仍按 passive 语义工作；LuCI benchmark 页面正常路径不受影响。
3. **L1**：`history` 的 `limit` 为负数或 0 时返回 `invalid-limit`，不返回数据；正整数 `limit` 行为不变；新增测试覆盖。
4. **B1 测量前提**：测量容器中的 `ucode`、`libucode`、`luci-base` 与目标 OpenWrt 25.12.5 的版本对齐；至少验证 `ucode -e` 能调用 `fs.access`，且 LuCI 内置非 PM 路由不再 500。
5. **B1 页面证据**：LuCI 登录返回 200；Overview、Settings、Benchmark 三个页面均无 500；至少对一个只读控件执行提交，后端 ubus/config 响应可验证；保存截图、关键 DOM 和接口响应到 `local-evidence/`（本地证据，不默认提交）。
6. **B1 兜底判定**：若版本对齐后 LuCI 内置路由仍 500，记录 `BLOCKED-ENVIRONMENT`，附版本矩阵和内置路由同样失败的证据；不得写成 PM 产品 PASS，也不得据此声称 UI 已验证。
7. `make test` 全部通过，测试数不少于 181 + 本阶段新增数；`make audit` PASS，并在本阶段代码提交上重新生成、提交快照（否则 H1 立即回退）。

**条件**：本地即可（Docker `linux/amd64` + OpenWrt 25.12.5 portable rootfs；不需要真机）。

**预计改动文件**：
- `package/performance-manager/files/usr/sbin/performance-manager.uc`（M5、M6、L1）
- `tests/`（错误语义、benchmark 参数、history 边界）
- `tools/docker-validate/`（仅在需要固定 ucode/LuCI 版本时）
- `package/luci-app-performance-manager/htdocs/luci-static/resources/view/performance-manager/*.js`（仅在页面实测发现真实 UI 缺陷时）
- `local-evidence/*`（本地证据，按需更新）
- `docs/FINAL_AUDIT.*` 等（阶段末重新生成）

**回退方式**：
- M5/M6/L1 每个修复独立提交，可单独 revert。
- 页面测试只做可逆操作；Settings 提交前先保存 `/etc/config/performance-manager` 的 md5 和副本，测试后恢复。
- 若 B1 仍被环境阻断，保留 `BLOCKED-ENVIRONMENT` 记录，不进入“UI 已验证”的发布叙事；阶段 2 以“记录清楚”为出口，不以“强行 PASS”为出口。

---

### 阶段 3：契约与文档对账（H2, H3, M1, M2, M4, L2, L3）

**目标**：只保留一个权威 Rill pin，让最终证据携带它，并让所有“当前状态”文档与代码/CI 一致。

**包含条目**：H2、H3、M1、M2、M4、L2、L3。

**前置/依赖**：阶段 2 完成，代码和测试数已稳定；否则本阶段冻结的测试数和 Core 字节数会立即过期。

**出口条件（全部可判定）**：

1. **H2 单一契约**：`contracts/rill-runtime.json` 成为唯一权威；把 `rill-dependency.json` 中仍需要的 `protocol`、`security` 等字段合并进去；删除 `contracts/rill-dependency.json`；`grep -R "rill-dependency" scripts .github package` 为零（历史 CHANGELOG 可保留历史叙述）。
2. **H3 pin 进证据**：`scripts/rill_contract_check.py` 生成 `releasePinStructureVerdict`（校验 schemaVersion、40 位 package commit、整数 packageRelease、qualification runId/verdict、40 位 upstream commit）；`docs/rill-integration-status.json` 含该字段且为 `PASS`；`scripts/final_audit.py` 渲染出非 `None`；`aggregate_final_evidence.py` 从 `contracts/rill-runtime.json` 读取并写入 pin 的 `commit`、`packageRelease`、`qualification.runId`、`resolved.version`，使 `final-release-evidence.json` 可独立核对。
3. **H3 验证**：在阶段 2 的最终代码 commit 上重跑 CI 的 `rill-runtime-v3` / `production-core-rill-integration`，下载最终证据，确认 pin 字段与契约逐字段相等。
4. **M1**：`docs/IMPLEMENTATION_STATUS.md` 不再声称 “Actions pinned to SHAs”，改为“使用可读 major tag；禁止 SHA/latest/HEAD/main”；`python scripts/check_action_refs.py` PASS；`grep -R "pinned to SHAs" docs` 为零。
5. **M2**：`ROADMAP.md` 的 CI job 名与 `ci.yml` / `build-openwrt.yml` 的实际 job 名逐字一致（`static`、`rill-runtime-v3`、`production-core-rill-integration`、`openwrt-sdk-build`）。
6. **M4**：`docs/TEST_PLAN.md` 删除 `cargo test/check --locked` 门禁；列出的每个 CI 门禁都能在仓库内找到可执行命令；`grep -n "cargo test\|cargo check" docs/TEST_PLAN.md` 为零。
7. **L2**：`local-evidence/` 只保留一个带当前 commit 的权威记录；另一个明确标记 `superseded` 或按用户确认移除；空的 `docker 3/`、`source 3/` 清理；不再出现同一时间点一个 PASS、一个 BLOCKED。
8. **L3**：当前文档不再把 `docs/rill-provenance.json` 的 `1.5.1` 当作当前 pin；该文件保留为 `historical-only` 或移入历史目录；当前叙述统一引用 `contracts/rill-runtime.json` 的 `1.5.6`。
9. `make audit` 在阶段 3 的最终提交上幂等；`python scripts/validate_contracts.py`、`python scripts/source_gates.py`、`python scripts/rill_contract_check.py` 全部 PASS。

**条件**：本地即可；需要一次 CI 重跑来验证最终证据，但**不需要改 CI 工作流**。优先只改脚本和数据；若确实必须改 workflow，单独提交并单独评审，不与本次审计收敛混在一起。

**预计改动文件**：
- `contracts/rill-runtime.json`（合并字段）
- `contracts/rill-dependency.json`（删除）
- `scripts/rill_contract_check.py`（写 `releasePinStructureVerdict`）
- `scripts/final_audit.py`（渲染字段）
- `scripts/aggregate_final_evidence.py`（写入 Rill pin）
- `docs/rill-integration-status.json`、`docs/FINAL_AUDIT.md`（生成）
- `docs/IMPLEMENTATION_STATUS.md`、`ROADMAP.md`、`docs/TEST_PLAN.md`
- `docs/rill-provenance.json`（历史标记/归档）
- `local-evidence/*`（仅本地整理，是否提交由用户决定）
- `tests/`（契约字段与证据聚合测试）

**回退方式**：
- 契约合并与文档修改分开提交；任何一项失败可单独 revert。
- 删除 `rill-dependency.json` 前保留 git 历史；若合并字段导致验证失败，先恢复旧文件，H2 不关闭。
- 证据聚合改动失败时，回退脚本提交，保留原有 CI 证据格式；不得用假 pin 填字段。

---

### 阶段 4：设备证据（M3, B2）

**目标**：在真实 OpenWrt 目标上给 `diagnostics` 超时定性，并产出 target/sysupgrade/soak 的真实结论或诚实的 `NOT_EVALUATED`。

**包含条目**：M3、B2。

**前置/依赖**：阶段 2 的 Core 行为修复和阶段 3 的契约/证据链完成；否则设备上采到的证据无法与最终 pin 对齐。

**执行前快照（必须记录原值）**：
- `uci export`、`/etc/config/performance-manager` 的 md5、相关 `sysctl` 原值、服务状态、已安装包列表。
- 记录回滚命令：恢复配置副本、恢复 sysctl、重启服务/设备。
- 任何会改变系统行为的测试必须可逆；优先使用一次性 VM/第二台设备。

**出口条件（全部可判定）**：

1. **M3 定性**：在真实 x86_64 OpenWrt 25.12.x 上分别测量 `ubus call performance-manager diagnostics` 的默认超时与 `-t 120` 的实际耗时；记录 rc、耗时、调用时的负载和配置。
2. **M3 结论**：二选一并写入证据：
   - `PRODUCT_DEFECT_FIXED`：若默认路径确实超时，减少 `diagnostics()` 的聚合范围/增加缓存/调整默认超时，并附修复前后同一设备的对比数据；
   - `ENVIRONMENT_ONLY`：若真机在默认超时内完成，记录容器模拟环境差异，关闭该项，不再把容器 30s 当作产品缺陷。
3. **B2 target gate**：`scripts/openwrt-target-gate.sh` 在目标矩阵上执行，逐项记录 OpenWrt/x86_64 身份、Core 启动/ubus、Analyzer/Topology/Packet Steering、Rill 停止时 Core 存活、stale lock 等结果。
4. **B2 sysupgrade**：`scripts/openwrt-sysupgrade-gate.sh prepare` → 真实 sysupgrade/reboot → `verify`，证明启动变化、配置/PM/Rill 持久化根保留、无 stale lock/pending marker；失败则记录具体阶段。
5. **B2 soak**：`scripts/openwrt-resource-soak.sh` 跑满 24h+（或明确记录缩短时长的开发证据，不得冒充 24h）；记录 RSS、CPU、Runtime 调用/失败/超时、持久化写入预算。
6. **B2 判定**：若声称 Stable，`final_release_audit.py` 必须在同一 commit 的聚合证据上给出 `stableReleaseVerdict=PASS`；否则必须明确写出 `stableReleaseVerdict=NOT_EVALUATED` 和缺失的具体 gate，不得用 portable 证据替代 hardware 证据。
7. 若本阶段修改了 Core 代码，必须在修改后的 commit 上重新执行 `make audit` 并提交快照；否则 H1 回退。
8. `docs/RELEASE_CHECKLIST.md` 的勾选状态与实际证据一致：不能出现“未跑但勾选”，也不能把 portable 结果写成 hardware PASS。

**条件**：需要真机（真实 OpenWrt x86_64 25.12.x；Hyper-V/KVM、sysupgrade、24h soak 按可用资源分步执行）。

**预计改动文件**：
- `package/performance-manager/files/usr/sbin/performance-manager.uc`（仅当 M3 确认为产品缺陷）
- `tests/`（M3 修复的回归测试）
- `scripts/openwrt-target-gate.sh`、`scripts/openwrt-sysupgrade-gate.sh`、`scripts/openwrt-resource-soak.sh`（仅当门禁脚本本身有缺陷）
- `docs/RELEASE_CHECKLIST.md`（按真实结果勾选/留空）
- 设备证据 JSON / 日志（按仓库现有 evidence 约定存放）
- `docs/FINAL_AUDIT.*`（若代码改动后重新生成）

**回退方式**：
- 设备侧：按执行前快照恢复配置、sysctl、服务；sysupgrade 测试使用可重装的 VM/备用设备，不拿唯一生产设备做首个实验。
- 代码侧：M3 修复独立提交，失败即 revert；不要在同一提交里混入其他修复。
- 若 24h soak 失败，停止后续发布步骤，记录 FAIL；不得用缩短时长的结果替代 24h。

---

### 阶段 5：发布决策与最终封存（B3, H4；复验 H1/L4）

**目标**：对 v1.0.4 做出明确的发布/不发布决策，让 README 与实际资产一致，并在干净工作树上封存最终审计快照。

**包含条目**：B3、H4；同时复验 H1、L4，确保前面的代码/设备改动没有把基线重新弄脏。

**前置/依赖**：阶段 4 完成；B3 需要发布权限；H4 依赖 B3 的决策分支。

**H4 与前序条件的关系（必须写清楚）**：
- 如果 **B3 执行发布**：README 必须匹配发布工作流实际产出的三架构资产命名（`performance-manager-all-v{version}-{arch}.apk`），并用 `gh release view` 核对每个文件名真实存在。
- 如果 **B3 不发布**：H4 仍然要关闭，但关闭方式是**把 README 改成指向实际存在的 v1.0.3 资产**（`luci-app-performance-manager-all-1.0.3-r1.apk`，且明确只有 x86_64），并删除/标注尚未存在的三架构下载承诺；不能继续写一个从未发布过的文件名。
- 如果 **B2 未 PASS**：不得发布 Stable；只能发布 portable/prerelease，或在 release notes/README 中明确 `stableReleaseAuthorized=false`、`hardwareCoverage=NOT_EVALUATED`。

**出口条件（全部可判定）**：

1. **B3 决策记录**：在计划/issue/release notes 中明确“发布 v1.0.4”或“不发布 v1.0.4”，并记录依据（B2 结论、发布权限、目标架构）。
2. **发布分支（若执行）**：
   - 产出并发布三个归一化 APK（`x86_64`、`aarch64_generic`、`aarch64_cortex-a53`）及 `SHA256SUMS.txt`；
   - `gh release view` 的资产名与 README 命令逐字一致；
   - 下载至少一个 APK 验证 SHA-256，并确认包内容/身份与 build metadata 一致；
   - Stable 仅在阶段 4 的 hardware gate 全部 PASS 且 `final_release_audit.py` 给出 PASS 时使用；否则标记 portable/prerelease。
3. **不发布分支**：README 的下载命令、包名、架构说明与实际 v1.0.3 资产完全一致；不存在指向未发布文件的命令；`README.md` 中不再声称三架构可下载。
4. **H1/L4 最终封存**：
   - 在干净工作树上执行 `make audit`；
   - 提交最终快照后 `git status --porcelain` 为空；
   - 已提交 `docs/FINAL_AUDIT.json` 的 `.pmCommitSha` 等于最终 HEAD；
   - `dist/` 不在工作树中；
   - `make audit` 再跑一次无 diff。
5. **发布后证据**：最终证据中的 Rill pin 与 `contracts/rill-runtime.json` 一致；APK hash、manifest、source audit 与最终 commit 对齐。

**条件**：需要发布权限；最终封存本地即可。

**预计改动文件**：
- `README.md`（H4）
- `docs/RELEASE_CHECKLIST.md`（最终状态）
- `docs/FINAL_AUDIT.json`、`docs/FINAL_AUDIT.md`、`docs/source-audit.json`、`docs/HOST_SYNTAX_REPORT.json`、`docs/RESOURCE_BUDGET.json`、`docs/rill-integration-status.json`（最终生成）
- `.github/workflows/prerelease.yml` / `stable-release.yml`（仅当发布资产命名逻辑本身有 bug；属于单独评审的 CI 改动）
- 发布资产与 checksums（仓库外/Release）

**回退方式**：
- 发布前用 draft release + `release-assembly-dry-run` 核对资产；发布前发现命名错误，删除 draft 即可。
- 已发布后不重写历史、不强制移动 tag；如命名错误，发更正 release 并在 README 说明。
- tag 删除只在获得明确授权后执行。
- 最终快照异常时 revert 快照提交并重新生成；不 amend。

## 4. 验收口径与禁止事项

- **PASS** 只接受可复现的命令输出、文件哈希、CI artifact 或设备证据；不接受“看起来应该没问题”。
- **BLOCKED** 必须带：阻塞原因、已尝试的命令、环境版本、下一步触发条件；不能只写“需要设备”。
- **NOT_EVALUATED** 是合法结论，但不能被写成 PASS；portable 证据不能授权 Stable。
- 本轮不 push、不发版、不改 CI、不触碰真实设备；设备阶段的所有改动必须先记录原值和回滚命令。
- 阶段 1 的生成物处理必须等用户确认；当前脏工作树中的 6 个 `docs/*` 和 `dist/` 原样保留，不在本轮丢弃。

## 5. 计划完成定义

当且仅当以下同时成立，审计问题才算收敛：

1. H1–H4、M1–M6、L1–L4 全部有明确状态（PASS / 已修复 / 明确 NOT_EVALUATED / 明确 BLOCKED 且有触发条件），没有“知道了但没排”的条目。
2. 三个 BLOCKED 项都有可判定结论：B1 页面实测 PASS 或 `BLOCKED-ENVIRONMENT` 证据；B2 至少给出逐 gate 的 PASS/FAIL/NOT_EVALUATED；B3 给出发布/不发布决策。
3. 最终提交的审计快照与 HEAD 一致，工作树干净，`make audit` 幂等。
4. README、ROADMAP、IMPLEMENTATION_STATUS、TEST_PLAN、RELEASE_CHECKLIST 不再包含与代码/CI/实际 release 冲突的当前状态描述。
