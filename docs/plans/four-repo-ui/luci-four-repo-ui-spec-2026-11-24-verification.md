# 四仓 UI 设计规范 · 核对报告

- 核对对象：`luci-four-repo-ui-spec-2026-11-24.md`（共享原件）落地的四份副本
  `docs/UI_DESIGN_SPEC.md`（PM / CFI / NGINX / UPNP）
- 核对日期：2026-11-24
- 目的：确认规范里的**可机检事实**与四仓当前代码一致，再决定是否放行
- 结论：**10 项机检 × 4 仓全部 PASS**；核出 2 处文档与代码不符，已修正并提交；
  人工视觉与实机部分（E-2）不在本报告范围，仍是最终放行的必要条件

---

## 1. 核对方法

规范有三类内容，只有前两类可机检：

| 类别 | 内容 | 核对方式 |
|---|---|---|
| 事实表 | 「本仓落点」的路由根、视图目录、CSS 路径、缓存键、i18n、门禁与构建文件 | 解析表格里的反引号路径，逐个落到文件系统 / `menu.d/*.json` / 源码字面量比对 |
| 否决清单 | §13 里 grep 可判的 A-1、T-1、H-1 | 对四仓插件 CSS 直接 grep |
| 判定条款 | §1–§12 的规则与 §14 来源索引 | 引文回查 `luci-four-repo-ui-goal-2026-11-15.md`，比对引用行号 |

检查脚本是临时脚本（未入库），因为它检查的是**文档自身是否属实**，不是产品的回归门禁；
产品门禁仍是各仓既有 `tests/` 与 `make lint`。

---

## 2. 事实表矩阵（4 仓 × 10 项）

| 检查项 | PM | CFI | NGINX | UPNP |
|---|:--:|:--:|:--:|:--:|
| 路由根在 `menu.d` 里存在 | PASS | PASS | PASS | PASS |
| 路由行列举的子页都在菜单里 | PASS | PASS | PASS | PASS |
| 视图目录存在且有文件 | PASS | PASS | PASS | PASS |
| 共享 CSS 路径存在 | PASS | PASS | PASS | PASS |
| 缓存键字符串与源码**逐字**一致 | PASS | PASS | PASS | PASS |
| i18n 目录（含各语种）齐 | PASS | PASS | PASS | PASS |
| UI 门禁与构建文件都存在 | PASS | PASS | PASS | PASS |
| A-1 插件 CSS 无 `body.theme-*` | PASS | PASS | PASS | PASS |
| T-1 表头未被重设 | PASS | PASS | PASS | PASS |
| H-1 无直接写死的颜色 | PASS | PASS | PASS | PASS |

逐字比对过的缓存键（规范写的 = 代码里的）：

- PM `?ui=pm-overview-rhythm-v7`（`performance-manager/ui.js:17`）
- CFI `?v=@PKG_FULL_VERSION@&ui=proxy-action-layout-2`（`cloudflare-ip/utils.js:540`）
- NGINX `?v=@PKG_FULL_VERSION@&ui=footer-pm-match-1&credentials=1&files-mobile-cards=6&toolbar-clearance=2&test-panel=4`（`nginx-manager/utils.js:71`）
- UPNP `?v=@PKG_FULL_VERSION@&ui=footer-pm-match-1`（`upnp-nat-relay/utils.js:155`）

> 缓存键写错是这份规范里代价最高的一类错误：抄漏一个 `&` 后缀，读者会以为改了 CSS 只要动
> `ui=`，实际还有五个功能后缀。所以这条按逐字比对，不做语义比对。

---

## 3. 核出的两处不符（已修正）

### 3.1 CFI 路由行把视图名当成了路由名

原文：`overview / settings / advanced / sources / intelligence / diagnostics(logs) / openclash / passwall`

实际：菜单键只有 `logs`，它指向视图 `cloudflare-ip/diagnostics`；`diagnostics` 不是菜单键。
另外 `passwall2`、`homeproxy` 两个菜单项已经存在但没被列举。

改为：`… / intelligence / logs（视图是 diagnostics.js，路由名与视图名在此不一致）/ openclash / passwall / passwall2 / homeproxy`
提交：`75201dd`

### 3.2 NGINX 路由行把路由写成了「页面名」

原文：`overview / sites / sites-edit / certificates / …`

实际：菜单键是 `admin/services/nginx-manager/sites/edit`（`title` 为 `null`），视图文件是
`site-edit.js`。原文的 `sites-edit` 两头都不对，也正是这一页在矩阵里反复被漏掉的原因。

改为：`overview / sites / sites/edit（视图 site-edit.js，该路由无菜单标题，需按路由直达验证）/ certificates / …`
提交：`8a24436`

其余两仓（PM、UPNP）的路由行与菜单、视图完全对得上，未改动。

---

## 4. 附带的旁证（不是缺陷，记录以免下次重查）

- **四仓裸十六进制颜色全部是自定义属性定义**（`--ys-footer-blue: #2f7df6`、NGINX 的
  `--nm-code-*` 代码高亮令牌，明暗两套）。没有一处把 hex 直接写进 `color`/`background` 声明，
  所以 H-1 成立：颜色仍走变量层，主题仍能接管。
- **`body:has(.floating-toolbar:not(.collapsed))` 只在 NGINX 出现一处**，正是规范 A-3 表里
  「浮动工具条压住插件自有路径输入框」那条裁决的实现，条件写的是页面状态而不是主题名，符合 A-4。
  PM/CFI/UPNP 没有这类规则，也就没有可违反的地方。
- **`text-transform: uppercase` 在 NGINX CSS 只有 1 处**，作用在 `.nm-test-level`（配置检测
  日志的级别标签），不是表头。T-1 判的是表头，这条属于插件自有组件的排版，不构成否决。
- **`aria-pressed` 只有 UPNP 用到**（向导 Safe/Auto 切换）。其余三仓当前没有需要表达选中态的
  自绘切换控件，不构成 X-4 缺口；一旦新增同类控件，这条要跟着补。

---

## 5. 共享正文一致性

四份副本去掉各自「本仓落点」头部后的正文：

```
tail -n +29 docs/UI_DESIGN_SPEC.md | shasum -a 256
PM / CFI / NGINX / UPNP  →  四份同为 0f3d29dd08b5ba40…
```

即规范承诺的「正文逐字一致，只多本仓落点」成立。以后改规则要四仓同改，任何一份单独动正文
都会在这里露出来。

---

## 6. 引文与来源索引回查

§1–§12 里带行号引用的 21 处引文逐条回查 `luci-four-repo-ui-goal-2026-11-15.md`：
引文能在原文找到，且落点行号与引用行号一致（`L52`/`L57` 是两个加粗小节标题，
`L151` 在 `L151–L152` 区间内，`L49`/`L55`/`L56` 为小节标题，均对得上）。

抽样复核：

| 规范位置 | 引文 | 原文落点 |
|---|---|---|
| §3 O-1 | 危险操作与高频刷新、筛选保持可辨识 | L33 |
| §4 S-1 | 信息不能只靠颜色 | L187 |
| §8 R-3 | 宽屏将可并列的相关控件同组排列… | L52 |
| §12 E-2 | 截图和交互 / 逐行记录 | L52 / L57 |

---

## 7. 本报告没有覆盖的部分

规范自己的 E-2 说得很清楚：一条 PASS 要同时有 exact SHA 的 Actions 成功、产物 SHA-256、
可打开的截图、逐行人工审阅、设备实机回看。本报告只完成了「规范文本是否属实」这一层，
**不能替代**下面这些：

1. 四仓当前候选包的 exact-SHA UI Gate 终态（PM `57716d3` 的 Real LuCI UI Gate 仍在跑，
   CFI `df23fbd` 的 UI 包构建成功但矩阵刚被新提交取代）。
2. 六主题 × 双语 × 断点矩阵的人工逐行审阅台账。
3. 设备实机回看（安装前后包/文件/UCI 配置 SHA 与服务状态，E-7）。

在这些补齐之前，规范的**文本**可以放行（已核、已修），但**界面**的放行仍按 E-2 走。
