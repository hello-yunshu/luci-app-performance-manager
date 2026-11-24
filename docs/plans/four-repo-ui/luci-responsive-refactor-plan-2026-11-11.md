# 四仓响应式改造实施方案（分阶段）+ 方案自审

> **本文档已被 `luci-native-first-plan-2026-11-12.md` 取代，保留作历史。**
> 以下手法已作废，不得按本文实施：`#maincontent` 前缀、选择器加倍、`data-label` 对抗 `attr(data-title)`、自定义 `@media`/`@container` 重排、自建暗色检测、插件侧 `select` 补丁。
> 本文的 P1–P7 批次划分、特异性结论与回滚方式均不再有效；测量数据可参考 `luci-responsive-breakpoint-audit-2026-11-11.md`。

- 日期：2026-11-11
- 依据：[luci-responsive-breakpoint-audit-2026-11-11.md](./luci-responsive-breakpoint-audit-2026-11-11.md)
- 约束：本文件只描述**未来实施者**的动作。当前会话保持只读，不改四仓、不提交、不切分支、不动设备配置。
- 原则：**每批可独立交付**。不存在“必须六批全做完才算完成”的结构；任何一批单独合入都不应让现状变差。

## 0. 前置纠正与门禁

### 0.1 两条前置纠正（先读，避免按旧说法改代码）

1. **导航只有 `.tabs` 一种**。`cbi-tabmenu` 不是第二种导航模型，全仓仅 `upnp/network` 有 2 组 section 内选项卡，宽度恒定不溢出，**本方案不处理它**。
2. **卡片同行高度不齐不成立**（实测同行高度差恒为 0）。**本方案不含任何等高 / `min-height` / JS 对齐改动**。

### 0.2 未验证项门禁

以下 5 项在任何文档、PR 描述、验收记录里都必须保留「未验证」标签，**不得被写成缺陷结论**：

| 编号 | 未验证项 | 本方案中的处理 |
|---|---|---|
| U1 | PM 表格窄屏行内行为 | P4 强依赖 P0-U1；未完成只能交付方案 A |
| U2 | bootstrap 主题 | 任何批次不得声称“兼容 bootstrap”；验收标 BLOCKED |
| U3 | 长目录名 / 长路径 | 不在任何批次里做“修复”，只做 P0 测量 |
| U4 | CF / UPNP 有数据行时的堆叠 | P2/P3 只能用真实行或合成行验证，结论注明范围 |
| U5 | 原生下拉展开态 | 不在批次内改动，只做 P0 观察 |

---

### 0.3 批次总览与依赖

| 批次 | 目标 | 涉及仓库 | 可否独立交付 | 依赖 |
|---|---|---|---|---|
| **P0** | 补测 5 个未验证项，产出基线 | 无（只跑测量） | ✅（不改代码） | 无；**P1/P2/P4 改动页的布局基线必须在对应批次合入前留档**；U1–U5 可与 P1/P2 并行，但 P4-B 必须在 U1 之后 |
| **P1** | 修 NGINX 表格 768–1024 死区、≤767 空标签、kv 表并排、空态 colspan | nginx-manager | ✅ | 无（P0 只影响验收完整度） |
| **P2** | 修 UPNP 表格同一问题（含 kv 表） | upnp-nat-relay | ✅ | 无（真实数据行验证依赖 P0-U4；合成行已验证 CSS） |
| **P3**（可选） | CF 媒体查询/容器查询去重 | cloudflare-ip | ✅ | **撤销原“启用死代码”目标**：容器查询已生效（`utils.js:579-581`）；只做等价去重，不改行为 |
| **P4** | PM 表格策略定稿并落地（含 768–1920） | performance-manager | ✅ | **U1 只影响堆叠方案**；卡片全宽/横滑方案不依赖 U1 |
| **P5** | 导航当前页签可见性 | 主题（上游）+ 四仓可选兜底 | ✅ | 5B 必须在 P1/P2 之后（同 view 文件） |
| **P6**（可选） | 收敛到原生契约、清理 NGINX 暗色板 | 四仓 | ✅ | P1/P2/P4/P7 |
| **P7** | PM `select` 210px 超出字段 3px | performance-manager | ✅ | 与 P4 同改 `ui.css`，必须串行（P4 先，P7 后） |

交付顺序建议：`P0 留档 → P1 → P2 → P1/P2 回归 → P4-A → P0-U1 → P4-B（若采用）→ P7 → P5 →（可选）P3 →（可选）P6`。P1/P2 可并行（不同仓库）；P4-A/B、P1/P6、P2/P6、P4/P7、P5B/P1/P2 都有文件级或 hunk 级重叠，**不可并行**。

> 隐含顺序（原方案没写）：P1/P2/P4 的布局基线必须在对应批次合入前采集（U1 可在 P1/P2 期间补测，但 P4-B 前必须有结论）；P4-B 必须在 P4-A 之后；P5B 必须在 P1/P2 之后；P6 必须在 P1/P2/P4/P7 之后；P7 必须在 P4 之后。违反顺序会导致“后做的批次改同一批 CSS，先做的批次无法单独 revert”。

---

## 1. 通用验收方法（每批都用这一套）

### 1.1 断点档位

必测 16 档：`320, 360, 390, 414, 480, 640, 767, 768, 820, 900, 901, 1024, 1025, 1280, 1440, 1920`
缩放等效 5 档：`312, 683, 853, 960, 1152`
明暗各跑一遍。

> 767/768、900/901、1024/1025 三组边界必须成对测。1920 是 P4 的必测档：PM 表格在 1280/1440/1920 仍是 497px 容器对 576px 表格，横滑 79px；不测 1920 会漏掉这个结论。

### 1.2 指标与阈值（每条都可用一个测量值判定）

| 指标 | 采集方式 | 通过标准 | 依据 |
|---|---|---|---|
| 页面级横向滚动 | `documentElement.scrollWidth - clientWidth` | `= 0`（全部 16+5 档） | 现状 0/1088 |
| 表格堆叠态 | `getComputedStyle(tr).display` | 堆叠区间 `block`；非堆叠区间 `table-row` | P1 修后实测 320/768 均为 `block`，1025 为 `table-row` |
| 单元格布局 | `getComputedStyle(td).display` | 堆叠区间 `flex`；非堆叠区间 `table-cell` | P1 修后实测一致 |
| 单元格 flex | `getComputedStyle(td).flexBasis` | 堆叠区间 `100%`；非堆叠区间 `auto` | 预修复实测 50%/auto，值区被挤 |
| 标签内容 | `getComputedStyle(td,'::before').content` | `!== 'none'` 且 `!== '""'`，且等于该列标题（含引号） | 预修复实测 `none`/`""` |
| 标签显隐 | `getComputedStyle(td,'::before').display` | 堆叠区间 `block`；非堆叠区间 `none` | Aurora 基础规则 `display:none` `(0,2,2)` |
| 标签宽度 | `::before` 的 `width` 与 `fontSize` | `abs(width - 7.2*fontSize) ≤ 2` 且 `60 ≤ width ≤ 120` | 修后实测 320=86px、768=98px；预修复 768=0px |
| 最窄可见列 | 遍历 `td`，过滤 `width>0` 取 `min` | 非堆叠区间 `min ≥ 60` 且无 `width < 40` | 1025/1280 实测 67/84；缺陷为 30 |
| 行高冗余 | `rowH - Σtd.getBoundingClientRect().height` | 堆叠区间 `≤ 32` | 修后实测 12–21；旧阈值 190–230 在 320 实测 329，作废 |
| 当前页签可见 | `active` 与 `ul` 的 `getBoundingClientRect()` | `active.left ≥ ul.left - 1 && active.right ≤ ul.right + 1` | 允许 1px 边框误差；不要求 `scrollLeft>0`（首个页签为 0 也应通过） |
| 按钮 | 最小高、小于 24×24 的数量 | `minH ≥ 32`，`tiny = 0` | 实测 1088 次全部成立 |
| `select` 溢出 | `select.right - field.right` | `≤ 0.5px` | 预修复 3px，加 `min-width:0` 后实测 0 |
| PM 容器横滑 | `wrap.scrollWidth - wrap.clientWidth` | P4-A：`≥1024` 时 `=0`，`<1024` 允许 `>0`；P4-B：全部 `=0` | 实测 1920 仍 79px |
| 容器查询生效 | `getComputedStyle(wrap).containerType` | P4-B 为 `inline-size` | `@container` 只在有容器的祖先上生效 |
| 控制台错误 | `page.on('pageerror')` / `console` | **只允许基线已有错误**，新增签名数 `=0` | 当前基线固定有 2 条 `"%s/%s.js%s".format is not a function`，不能要求 0 |
| 暗色生效 | `documentElement.dataset.darkmode` | 测量前必须为 `"true"`；不是则标 BLOCKED | 暗色由主题属性控制，不靠 `prefers-color-scheme` |

### 1.3 跑法

```bash
cd /tmp/luci-audit/runner
# 全量断点（明/暗）
REPO=nginx node audit3.js light
REPO=nginx node audit3.js dark
# 契约断言（退出码 0=全过，1=至少一条失败）
node assert.js nginx 320,360,390,414,480,640,767,768,820,900,901,1024,1025,1280,1440,1920 light
node assert.js upnp  320,360,390,414,480,640,767,768,820,900,901,1024,1025,1280,1440,1920 light
node assert.js pm    320,360,390,414,480,640,767,768,820,900,901,1024,1025,1280,1440,1920 light
```

- `assert.js` 的当前可运行副本：`/tmp/luci-audit/runner/assert.js`（本会话已跑通，基线 `EXIT=1`）。
- 暗色：登录后用主题开关切换，并在每次测量前断言 `dataset.darkmode === 'true'`；直接设置属性可能被主题初始化覆盖，设置后需等 200ms 再断言。
- 每个批次合入前先跑一次，记录失败项作为 before；合入后再跑，要求 before 的失败项全部消失且无新增失败。

### 1.4 截图规范

- 目录：`/tmp/luci-audit/shots/<批次号>/`
- 命名：`<before|after>-<mode>-<width>-<repo>-<page>.png`
- 每批至少留：`320`、`640`、`768`、`1024`、`1280`、`1920` 六个宽度 × 明暗 × 改动页。
- 截图前固定：`viewport` 固定、`prefers-reduced-motion: reduce`、等待 `#maincontent` 后再等 400ms。
- 截图是评审证据，不是回归断言；回归断言由 1.6 的脚本承担。若要用截图做基线，使用 Playwright `toHaveScreenshot({ maxDiffPixelRatio: 0.001 })`，且基线必须与当前主题版本绑定。

### 1.5 回滚（含冲突处理）

- CSS/JS 都是静态资源，**无数据迁移、无配置变更**。
- 单批 = 单仓单提交；**只有在没有后续批次改过同一 hunk 时，才能直接 `git revert <commit>`**。
- 同文件/hunk 重叠关系：

| 先做的批次 | 后做的批次 | 重叠点 | 直接 revert 先做批次的结果 |
|---|---|---|---|
| P1 | P6 | `nginx-manager.css` 423–501 整块 | 冲突；P6 已删除该块 |
| P2 | P6 | `upnp-nat-relay.css` 352–401 整块 | 冲突；P6 已删除该块 |
| P4-A | P4-B | `ui.css` 153–157 与新增堆叠块 | 冲突；B 基于 A 的卡片全宽规则 |
| P4 | P7 | `ui.css` 同一文件 | 可能冲突；按逆序先 revert P7 |
| P1/P2 | P5B | NGINX/UPNP 的 view JS | 可能冲突；5B 在渲染收尾处插代码 |

- **逆序回滚**：`P6 → P7 → P5B → P4-B → P4-A → P2 → P1`。先 revert 最后合入的批次，再往前。
- 若 P6 已合入，P1/P2 的 CSS 部分已被 P6 删除，**不要单独 revert P1/P2**：回滚单元变成 P6；revert P6 会同时恢复 P1/P2 的 CSS，此时再决定是否继续回滚 P1/P2。
- 冲突时的可行写法（以 P6 后回滚 P1 为例）：
  ```bash
  git revert --no-commit <P1-sha>
  # 冲突文件保留 P6 的删除结果（即不要恢复 P1 的 CSS），只回滚 P1 的 JS 改名
  git checkout --ours -- www/luci-static/resources/nginx-manager/nginx-manager.css
  git add -A && git commit -m "revert: P1 (JS only; CSS superseded by P6)"
  ```
  若目标是回到 P1 合入前的状态，则必须连 P6 一起回滚，不能只回 P1。
- 容器验证环境：`docker cp` 恢复原文件或重建包，再跑 1.3 的 16 档确认恢复原状。

### 1.6 回归保护（可执行，不是口头约定）

每批合入前把 `assert.js` 复制到该仓的 `scripts/responsive-assert.js`，并提供 `npm run assert:responsive` 或 `make assert-responsive`；CI 里对改动页跑 16 档，**退出码非 0 即失败**。

脚本核心逻辑（完整可运行版见 `/tmp/luci-audit/runner/assert.js`；PM 需要按 P4 的 wrap/容器断言扩展，`stackMax:0` 只表示“表格态”）：

```js
// scripts/responsive-assert.js
const { chromium } = require('playwright');
const T = {
  nginx: { path: '/cgi-bin/luci/admin/services/nginx-manager/files', sel: '.nm-responsive-table', stackMax: 1024 },
  upnp:  { path: '/cgi-bin/luci/admin/services/upnp_nat_relay/mappings', sel: '.ubr-responsive-table', stackMax: 900 },
};
const W = (process.env.W || '320,360,390,414,480,640,767,768,820,900,901,1024,1025,1280,1440,1920').split(',').map(Number);
const probe = (sel) => {
  const t = document.querySelector(sel); if (!t) return { missing: true };
  const tr = [...t.querySelectorAll('tr')].find(r => r.querySelector('td')); if (!tr) return { missing: 'no-row' };
  const tds = [...tr.children], pb = getComputedStyle(tds[0], '::before');
  return { tr: getComputedStyle(tr).display, td: getComputedStyle(tds[0]).display,
    basis: getComputedStyle(tds[0]).flexBasis, content: pb.content, labelDisp: pb.display,
    labelW: parseFloat(pb.width) || 0, labelFs: parseFloat(pb.fontSize) || 0,
    rowH: Math.round(tr.getBoundingClientRect().height),
    tdSumH: tds.reduce((s, x) => s + x.getBoundingClientRect().height, 0),
    widths: tds.map(x => Math.round(x.getBoundingClientRect().width)) };
};
// login -> goto(T[repo].path) -> for each W: setViewportSize; evaluate(probe)
// fail if: page overflow !==0; stacked && (tr!=='block'||td!=='flex'||basis!=='100%'||
//   labelDisp!=='block'||content in ('none','""')||Math.abs(labelW-7.2*labelFs)>2||rowH-tdSumH>32);
// table && (tr!=='table-row'||td!=='table-cell'||labelDisp!=='none'||min(widths)<60||widths.some(w=>w>0&&w<40))
// process.exit(failed ? 1 : 0)
```

本次已实际跑出的基线（修前，NGINX files，light）：

```text
320  tr=flex td=block basis=50%  content=""  label=none width=118  widths=[126,126,126,126,126,126]  -> FAIL
768  tr=block td=table-cell basis=auto content="" label=none width=0 widths=[76,87,30,52,155,239] -> FAIL
1024 tr=block td=table-cell basis=auto content="" label=none width=0 widths=[76,89,30,53,158,243] -> FAIL
1025 tr=table-row td=table-cell label=none widths=[224,91,67,68,180,277] -> PASS
1280 tr=table-row td=table-cell label=none widths=[285,115,84,86,229,352] -> PASS
EXIT=1
```

回归保护同时包含两条静态守卫：

1. `grep -rn "data-label" <repo>/www <repo>/package/**/htdocs` 在 P1/P2 合入后必须为 0（探针脚本除外）。
2. 主题契约探针：在 767 宽度断言 Aurora 的 `tr` 为 `flex`、`td` 为 `block`；若主题升级改变了 48rem 契约，断言先失败，提醒重新审计，而不是让插件规则悄悄失效。

---

## 2. P0：补测未验证项（不改代码）

### 2.1 范围与目标

把审计报告第 2 节的 U1–U5 从「未验证」变成「已验证」或「确认无法验证」。**本批不产出任何代码改动**，只产出测量数据与结论。

### 2.2 具体做法

| 编号 | 做法 | 产出 | 失败时 |
|---|---|---|---|
| **U1** PM 表格行内行为 | 在容器内用 `uci add performance-manager ...` 造 3–5 条历史/排名记录（只改容器，不碰真实设备），重启 rpcd，再跑 `nf.js` 同款探针 | 320/480/600/768 下的列宽、行高、换行、按钮挤压截图 | 若 RPC 仍返回空，标注「无法在容器内造数」，P4 降级为只做横滑优化 |
| **U2** bootstrap | 先修 harness 模板（当前 500 是打包缺陷），或换官方 OpenWrt 25.12.5 镜像装 bootstrap；只测 `nginx/files` 与 `pm/rill` 两页 | 320/768/1024 三档截图 + 表格 `display` 值 | 修不好就保持「未验证」，**不得**写“bootstrap 已通过” |
| **U3** 长路径 | 在容器 `/www/` 下创建 60/80 字符目录名与 3 层深目录，访问 nginx `files` 页 | 320/768 下是否截断、是否撑破、`scrollWidth` 实测 | 无法创建则标注「受容器权限限制」 |
| **U4** CF/UPNP 数据行 | 给 `cf_ip` 注入假 `source-registry` 返回；给 UPNP 写一条 `miniupnpd` 租约；再跑探针 | 堆叠态真实行截图 + 标签内容 | 注入失败则保留「合成 DOM 结论」，仍标未验证 |
| **U5** 下拉展开态 | Playwright 点击 MultiValue 箭头，展开后测 `ul.dropdown` 的 `getBoundingClientRect()` 与视口关系 | 320/480 下是否溢出、是否被裁、是否可滚 | 展开面板无选项时标注「无选项数据」 |

### 2.3 验收

- 每项产出：`/tmp/luci-audit/p0/<U#>-<width>-<page>.png` + 一行结论（已验证/仍不可验证）。
- 更新审计报告的「未验证项」表：已验证的移出，仍不可验证的保留标签。
- **门禁**：U1 未完成前不得进入 **P4-B**（P4-A 的卡片跨列不依赖 U1，可先做）；U2 未完成前任何批次都不得声称兼容 bootstrap。

### 2.4 回滚

无代码改动，无需回滚。容器内造的测试数据在容器废弃时一并丢弃。

---

## 3. P1：nginx-manager 表格止血（最小可交付）

### 3.1 范围与目标

修掉唯一能完整实证的破版：`files` 页在 768–1024 退化为 6 列挤扁、≤767 标签为空。

**不做**：不重写布局、不动暗色、不动文案。

### 3.2 涉及文件

| 文件 | 行 | 动作 |
|---|---|---|
| `luci-app-nginx-manager/www/luci-static/resources/view/nginx-manager/files.js` | 468–478、557–575 | `data-label` → `data-title`（12 处） |
| `luci-app-nginx-manager/www/luci-static/resources/view/nginx-manager/sites.js` | 全文 | `data-label` → `data-title`（7 处） |
| `luci-app-nginx-manager/www/luci-static/resources/view/nginx-manager/backups.js` | 全文 | 同上（3 处） |
| `luci-app-nginx-manager/www/luci-static/resources/view/nginx-manager/certificates.js` | 全文 | 同上（5 处） |
| `luci-app-nginx-manager/www/luci-static/resources/nginx-manager/nginx-manager.css` | 423–501 | `#maincontent` 前缀 + `display`/`flex`/`margin` 复位 + `attr(data-title)`；补 `td[colspan]` |
| 同上 | 480–500 | `.nm-kv-table` 的 `tr`/`th`/`td` 同样加 `#maincontent` 前缀（320 下 `tr=flex`、`th`/`td` 各 127px 并排，实测） |

### 3.3 具体改法

**第一步：属性改名（27 处 JS + 1 处 CSS）**

```diff
- E('td', { 'class': 'td', 'data-label': _('Size') }, ...)
+ E('td', { 'class': 'td', 'data-title': _('Size') }, ...)
```

**第二步：用 `#maincontent` 前缀 + 显式复位，而不是“选择器加倍”**

```css
@media (max-width: 1024px) {
  #maincontent .nm-responsive-table { display: block; overflow: visible; }
  #maincontent .nm-responsive-table thead { display: none; }
  #maincontent .nm-responsive-table tbody,
  #maincontent .nm-responsive-table tr { display: block; }

  #maincontent .nm-responsive-table td {
    display: flex;          /* 压过 Aurora 基础 td{display:table-cell} (0,2,1) */
    flex: 0 0 100%;         /* 压过 Aurora 窄屏 td{flex:50%} (0,2,1) */
    align-items: center; gap: .75em; padding: .28em 0;
    border: none; text-align: left; min-width: 0;
  }

  #maincontent .nm-responsive-table td::before {
    content: attr(data-title);
    display: block;         /* 压过 Aurora 基础 ::before{display:none} (0,2,2) */
    flex: 0 0 7.2em;
    margin-bottom: 0;       /* 压过 Aurora 窄屏 ::before{margin-bottom} (0,2,2) */
    font-weight: 600; text-align: left; white-space: normal;
    color: var(--subtext-color, #666); font-size: .85em; word-break: break-word;
  }

  /* files 页空目录是 td[colspan=6]，不加这条会多出一个 7.2em 的空标签位 */
  #maincontent .nm-responsive-table td[colspan] { display: block; }
  #maincontent .nm-responsive-table td[colspan]::before { display: none; }

  /* overview 的 kv 表：Aurora 窄屏 tr{display:flex} (0,2,1) 胜 .nm-kv-table tr (0,1,1) */
  #maincontent .nm-kv-table tr { display: block; }
  #maincontent .nm-kv-table th,
  #maincontent .nm-kv-table td { display: block; }
}
```

**为什么不能只“加倍 class”**（本轮用真实浏览器逐条验证）：

- Aurora 实际规则（`aurora-main.css`）：
  - `:is(table.table,.table) td, :is(table.table,.table) .td` → `(0,2,1)`（`.td` 分支抬高了外层 `:is`）
  - `:is(:is(table.table,.table) td, :is(table.table,.table) .td)::before` → `(0,2,2)`
  - 窄屏 `:is(:is(table.table,.table) tr, :is(table.table,.table) .tr)` → `(0,2,1)`
- `.nm-responsive-table.nm-responsive-table td` 也是 `(0,2,1)`，只是**平手**，靠源码顺序决胜；实测插件 CSS 在 `styleSheets` 索引 2、Aurora 在 0，平手时插件胜。换主题/换加载顺序就不成立。
- 平手仍有两个“未声明”漏洞：
  - 插件 `td::before` 只写了 `content`，没写 `display`；Aurora 的 `display:none` 继续生效 → 768–1024 标签仍不可见。
  - 插件 `td` 没写 `flex`；Aurora 窄屏 `flex:50%` 继续生效 → 320 下 `td` 仍是 126px 两列。
- 实测三种写法（320 / 768 / 1024）：

| 写法 | 320 | 768 | 1024 | 结论 |
|---|---|---|---|---|
| A：只加倍 class + `content`，不写 `display`/`flex` | 标签 86px、`flex-basis:50%` | `::before display:none`、宽 0、`td=flex` | 同 768 | **无效**，768–1024 标签仍不可见 |
| C：加倍 class + `display:block` + `flex:0 0 100%` | 标签 86px、basis 100% | 标签 98px、basis 100% | 同 768 | 本环境通过，但依赖源码顺序 |
| B：`#maincontent` 前缀 + `display:block` + `flex:0 0 100%` | 标签 86px、basis 100% | 标签 98px、basis 100% | 同 768 | **采用**，与源码顺序无关 |

特异性：`#maincontent .nm-responsive-table td` = `(1,1,1)`，`... td::before` = `(1,1,2)`，分别高于 Aurora 的 `(0,2,1)` / `(0,2,2)`。CF 的 `#maincontent .cfi-status-banner.running` 已经用同一手法压过 `#maincontent .cbi-section`，说明该前缀在本主题下可用。

**不要在本批加 `data-title` 却保留 `data-label`**：同一个元素只有一个 `::before`，两条 `content` 规则只会有一条生效，保留双属性会让调试时误判。

### 3.4 验收

| 宽度 | 期望（可直接用 1.2 的测量值判定） |
|---|---|
| 320 / 390 / 480 / 640 / 767 | `tr=block`、`td=flex`、`flexBasis=100%`、`::before content="Name"` 等非空、`::before display=block`、`abs(width-7.2*fontSize)≤2`、`rowH-ΣtdH≤32` |
| 768 / 820 / 900 / 1024 | 同上（堆叠后不再出现 30px 列） |
| 1025 / 1280 / 1440 / 1920 | `tr=table-row`、`td=table-cell`、`::before display=none`、`min(td width)≥60` 且无 `width<40` |
| 全部 16+5 档 | `documentElement.scrollWidth - clientWidth = 0` |
| kv 表 | 320 下 `tr=block`、`th`/`td=block`（不再 127/127 并排）；768 下同样 `block` |
| 空态 colspan | `td[colspan]::before` 的 `display=none`；若无空目录，用 DOM 注入一行 `td[colspan=6]` 后测 |
| Actions 列 | 3 个按钮两两不重叠（按 `left` 排序后 `right_i ≤ left_j`），最小高 ≥32 |

- 控制台：只允许基线已有 2 条 `"%s/%s.js%s".format is not a function`，新增签名数 `=0`。
- 截图：`shots/P1/before-*` 与 `after-*`，320/640/768/1024/1280/1920 × 明暗。
- 断言：`node assert.js nginx 320,360,390,414,480,640,767,768,820,900,901,1024,1025,1280,1440,1920 light` 退出码 0。

### 3.5 风险与回滚

| 风险 | 说明 | 应对 |
|---|---|---|
| 768–1024 由“表格”变“长卡片” | 页面显著变长，需要更多滚动 | 这是修好破版的必然结果；在 PR 里附 before/after 截图说明 |
| 27 处机械改名漏改 | 漏一处就有一列标签为空 | 1.6 的静态守卫 `grep data-label = 0` + 每列 `::before` 非空断言 |
| `#maincontent` 前缀在 modal 内失效 | modal 挂在 `#modal_overlay`，不在 `#maincontent` 内 | 本批只覆盖 `#maincontent` 内的表格；若后续 modal 复用表格，再加 `.modal` 前缀并补测 |
| 与 P6 冲突 | P6 会删除 423–501 整块 | P1 先合；P6 后合。P6 合入后 P1 的 CSS 不可单独 revert（见 1.5） |
| kv 表规则被顺手改坏 | 480–500 与主表相邻 | kv 表单独一段 diff，验收单独列 320/768 两项 |

回滚：P6 未合入时 `git revert <P1>` 可完全恢复；P6 已合入时按 1.5 逆序，先 revert P6，或只回滚 P1 的 JS 改名并保留 P6 的 CSS 删除。

---

## 4. P2：upnp-nat-relay 表格止血

### 4.1 范围与目标

与 P1 同构：`mappings` 页 `data-label` + `tr{display:block}` 被 Aurora 覆盖。

### 4.2 涉及文件

| 文件 | 行 | 动作 |
|---|---|---|
| `luci-app-upnp-nat-relay/package/luci-app-upnp-nat-relay/htdocs/luci-static/resources/view/upnp-nat-relay/mappings.js` | 全文 | `data-label` → `data-title`（16 处） |
| `luci-app-upnp-nat-relay/package/luci-app-upnp-nat-relay/htdocs/luci-static/resources/upnp-nat-relay/upnp-nat-relay.css` | 352–401 | `#maincontent` 前缀 + `display`/`flex`/`margin` 复位 + `attr(data-title)`；`td[colspan]` 同样加前缀 |
| 同上 | 402–430（`.ubr-kv-table` 段） | `tr`/`th`/`td` 加 `#maincontent` 前缀（320 下 `tr=flex`、127/127 并排，实测） |

### 4.3 具体改法

与 P1 完全一致，把 `.nm-responsive-table` 换成 `.ubr-responsive-table`，媒体查询保持 `max-width:900px`（不要顺手改成 768，先只做等价修复）。

```css
@media (max-width: 900px) {
  #maincontent .ubr-table-wrap > .ubr-responsive-table { display: block; min-width: 0; overflow: visible; }
  #maincontent .ubr-responsive-table tr { display: block; }

  #maincontent .ubr-responsive-table td {
    display: flex;
    flex: 0 0 100%;
    align-items: flex-start; gap: .75em; padding: .28em 0;
    border: 0; text-align: left; min-width: 0;
  }

  #maincontent .ubr-responsive-table td::before {
    content: attr(data-title);
    display: block;
    flex: 0 0 7.2em;
    margin-bottom: 0;
    color: var(--subtext-color, #666); font-size: .85em; font-weight: 600;
    text-align: left; white-space: normal; word-break: break-word;
  }

  #maincontent .ubr-responsive-table td[colspan] { display: block; }
  #maincontent .ubr-responsive-table td[colspan]::before { display: none; }

  #maincontent .ubr-kv-table tr { display: block; }
  #maincontent .ubr-kv-table th,
  #maincontent .ubr-kv-table td { display: block; }
}
```

**本轮实测（UPNP mappings 无真实数据行，用合成 `<tr>` 验证 CSS）**：

| 状态 | 320 | 768 / 820 / 900 | 901 / 1024 |
|---|---|---|---|
| 修前 | `tr=flex`、`td=block`、`basis:50%`、`::before content=""`、列宽 `[126×6]` | `td=table-cell`、`::before display=none`、宽 0 | `td=table-cell`、正常 |
| 修后 | 标签 86px、`basis:100%`、行高 184 | 标签 98px、`basis:100%`、行高 219 | `table-row`/`table-cell` |

- 合成行只能证明 CSS 契约，**不能**证明真实数据下无溢出；真实行仍需 P0-U4。
- 900 与 901 成对测：900 堆叠、901 表格，不出现差 1px 跳变。

### 4.4 验收

| 项 | 通过标准 |
|---|---|
| 320 / 390 / 480 / 640 / 767 / 768 / 820 / 900 | `tr=block`、`td=flex`、`flexBasis=100%`、`::before` 非空且 `display=block`、`abs(width-7.2*fontSize)≤2`、`rowH-ΣtdH≤32` |
| 901 / 1024 / 1280 / 1440 / 1920 | `tr=table-row`、`td=table-cell`、`::before display=none`、`min(td width)≥60` 且无 `width<40` |
| 空态 colspan | 三张表的 `td[colspan]::before display=none` |
| kv 表 | 320 与 768 下 `tr=block`、`th`/`td=block`（不再 127/127） |
| 页面横滚 | 全部 16+5 档 `=0` |
| 断言 | `node assert.js upnp 320,...,1920 light` 退出码 0 |

- 截图：`shots/P2/`，320/768/900/901/1024/1280 × 明暗。
- `mappings` 表有 `td[colspan]`（空态行）；加前缀后专门看空态行不出现 7.2em 空白标签位。

### 4.5 风险与回滚

- 风险：900px 断点与主题 768px 不一致，768–900 在主题是表格、插件是卡片；这是插件既有设计，本批不改断点，避免引入行为变化。
- 风险：`#maincontent` 前缀只覆盖主内容区；modal 内表格不在本批范围。
- 回滚：单提交 `git revert`；P6 合入后按 1.5 逆序。

---

## 5. P3（撤销）：cloudflare-ip 容器查询不是死代码

### 5.1 结论推翻

原方案写“`@container` 那套规则当前从不命中”，**错误**。证据：

- `utils.js:579-581` 的 `appendFooter` 已对任何 `.cbi-map`（排除 `.cfi-dashboard`）补 `cfi-form-map`：
  ```js
  if (node.classList && node.classList.contains('cbi-map') && !node.classList.contains('cfi-dashboard'))
    node.classList.add('cfi-form-map');
  ```
- `cloudflare-ip.css:525-527` 在 `@supports (container-type:inline-size)` 内给 `.cfi-dashboard,.cfi-form-map` 设 `container-type:inline-size`。
- 因此正常渲染路径命中 `@container (max-width:900px)`（555–610），不存在“死代码”。

### 5.2 本批改为可选去重（不改行为）

`@media (max-width:900px)`（418–484）与 `@container (max-width:900px)`（555–610）是两套等价实现。去重的前提是逐条对比两套规则在 900/901、1024、1280 下的计算样式完全一致；只要有一条不一致，就保留两套。

- 不做：不“启用”任何东西，不加 class，不改 `utils.js`。
- 若去重：只删其中一套，并在 PR 里附 900/901/1024/1280 的 before/after 计算样式对比。
- 验收：1024 侧栏展开时 `.cfi-source-table > .tr` 的计算 `display` 与去重前一致；1280 不堆叠。
- 回滚：`git revert`，无依赖。

**批次编号保留 P3 但标注撤销**，避免与报告/其他文档的编号错位；不再占用交付顺序。

---

## 6. P4：performance-manager 窄屏表格策略

### 6.1 范围与目标

PM 当前靠 `.pm-table-wrap{overflow-x:auto}` + `.table{min-width:36rem}` 横滑。此前写“1280 起不再横滑”是错的，实测（rill，fresh load）：

| 视口 | 320 | 480 | 640 | 768 | 820 | 900 | 1024 | 1152 | 1280 | 1440 | 1920 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| wrap `clientWidth` | 231 | 386 | 537 | 278 | 295 | 331 | 387 | 444 | **497** | **497** | **497** |
| 表格 `min-width` | 576 | 576 | 576 | 576 | 576 | 576 | 576 | 576 | 576 | 576 | 576 |
| 可横滑 | 345 | 190 | 39 | 298 | 281 | 245 | 189 | 132 | **79** | **79** | **79** |

根因不是断点，是布局：`.pm-table-wrap` 位于 `.pm-card-grid--primary` 的两列网格里（primary card 544px、内容列 499px），所以 **1920 下仍是 497px 容器对 576px 表格**。因此：

- **方案 A（默认，不需要 U1）**：≥1024 让表格所在卡片横跨两列（优先在 `rill.js` 给卡片加 `pm-card--wide`；不改 JS 时用 `:has(.pm-table-wrap)`），使容器 ≥576；<1024 保留横滑。
- **方案 B（需 U1）**：A 之上加容器查询，容器 <576 时堆叠。不要用视口断点：768–1024 的容器只有 278–387px，而 1920 的容器是 497px，视口阈值和容器宽度没有单调关系。
- **方案 C（A 的替代）**：不跨列，把 `min-width` 改成 `min(36rem,100%)`，让表格在 497px 内收缩，容器 <480 时堆叠。5 列各约 99px，是否可接受由 U1 决定。

### 6.2 涉及文件

| 文件 | 行 | 动作 |
|---|---|---|
| `luci-app-performance-manager/package/luci-app-performance-manager/htdocs/luci-static/resources/performance-manager/ui.css` | 153–157 | A：卡片跨列或 C：`min-width` 收缩；B：`container-type` + `@container` |
| `.../view/performance-manager/rill.js` | 25、30 | B：每个 `td` 加 `data-title`；A：给表格卡片加 `pm-card--wide`（若不用 `:has`） |

### 6.3 方案 A / B 的关键约束

**A：卡片跨列（先做）**

```css
@media (min-width: 1024px) {
  .pm-card-grid--primary > .pm-card:has(.pm-table-wrap) { grid-column: 1 / -1; }
}
```

- 预期：≥1024 时 wrap 从 497 变为约 1108，`576/1108`，横滑归零。
- 若目标浏览器不支持 `:has()`，在 `rill.js` 给该卡片加 `pm-card--wide`，CSS 改用 `.pm-card--wide{grid-column:1/-1}`；两种写法只选其一。
- 不做：不改表格列定义、不改 `min-width:36rem`。

**B：容器查询堆叠（依赖 A + U1）**

```css
.pm-table-wrap { container-type: inline-size; }

@container (max-width: 575px) {
  .pm-table-wrap .table { min-width: 0; }     /* 不去掉就会在 278px 容器里按 576px 排 */
  .pm-table-wrap thead { display: none; }
  .pm-table-wrap tr { display: block; }
  .pm-table-wrap td {
    display: flex; flex: 0 0 100%; gap: .75em;
    align-items: flex-start; min-width: 0; border: 0; text-align: left;
  }
  .pm-table-wrap td::before {
    content: attr(data-title); display: block;
    flex: 0 0 7.2em; margin-bottom: 0;
    color: var(--subtext-color, #666); font-size: .85em; font-weight: 600;
  }
  .pm-table-wrap td[colspan] { display: block; }
  .pm-table-wrap td[colspan]::before { display: none; }
}
```

```diff
- E('td', {}, [ String(i + 1) ])
+ E('td', { 'data-title': _('Rank') }, [ String(i + 1) ])
```

- 只加 `data-title` 不去掉 `min-width:36rem`，表格仍然 576px 宽，堆叠只是“在 576px 画布里堆”，等于没改。两处必须成对提交。
- `@container` 不能样式化容器自身，只能样式化后代；`container-type` 必须加在 `.pm-table-wrap` 上，不能加在 `.table` 上。

### 6.4 验收

| 方案 | 通过标准 |
|---|---|
| A | 视口 1024/1152/1280/1440/1920：`wrap.scrollWidth - wrap.clientWidth = 0`；320–1023：页面横滚 `=0`，允许 `wrap` 横滑（320 仍 345px） |
| B | 全部 16+5 档：页面横滚 `=0` 且 `wrap` 横滑 `=0`；`containerType=inline-size`；容器 <576 时 `tr=block`、`td=flex`、`::before` 非空且 `display=block`；容器 ≥576 时 `tr=table-row`、`td=table-cell`、`::before display=none` |
| C | 全部档 `wrap` 横滑 `=0`；容器 <480 堆叠；497 宽时表格不堆叠且 `min(td width)≥60`、无 `width<40` |

- 明暗两套；截图 320/480/640/768/1024/1280/1920。
- **U1 退路（必须写进 PR 描述）**：
  1. U1 造不出数据 → **只交付 A**，B 保留“未验证”，不得声称已堆叠。
  2. U1 显示真实行有嵌套表格/操作按钮导致 B 在 320/480 溢出 → **放弃 B**，保留 A。
  3. U1 显示空态 `colspan=5` 行 → B 必须保留 `td[colspan]::before{display:none}`。
  4. A 的跨列改动被 UI 评审拒绝 → 改用 C；C 的列宽是否可接受由 U1 的真实内容决定。
  5. A 在目标浏览器不支持 `:has()` → 用 `pm-card--wide` class，不降级为无修复。

### 6.5 风险与回滚

- 方案 B 会让 Rill 页在窄容器显著变长；空态行需要单独隐藏 `::before`。
- A 与 C 互斥，只选一个提交；B 基于 A，**顺序必须是 A → B**。
- 回滚：逆序，先 revert B（恢复横滑 + 保留 A 的跨列），再按需 revert A；只回滚 A 而保留 B 会冲突（B 的 `@container` 依赖 A 的宽容器预期），见 1.5。

---

## 7. P5：导航当前页签可见性

### 7.1 范围与目标

`.tabs` 溢出时浏览器不把 active 页签滚进视野（320 下 7/8 页不可见，768 下 5/8）。这是**主题层缺陷**，首选上游修。

### 7.2 两种交付

**5A（推荐，主题上游）**：给 Aurora 提 issue/PR——`#tabmenu ul.tabs` 初始化后对 `li.active` 执行 `scrollIntoView({inline:'nearest', block:'nearest'})`，或在渲染时设置 `ul.scrollLeft`。

**5B（插件兜底，可选）**：四仓各自新增一个共享 helper（约 15 行），由 view 的 `render()` 收尾调用；模块级 `installed` 标志保证只挂一次监听。缺点：四份重复，且属于“插件替主题擦屁股”，与既定方向相反。只有在 5A 明确排期过晚时才做。

### 7.3 验收

- 320/390/480/768 下抽查 8 个代表页，`active.left >= ul.left - 1 && active.right <= ul.right + 1`。
- **不要求 `scrollLeft > 0`**：首个页签本来就该是 0，用 `scrollLeft` 判分会把正确状态判失败。只判可见性。
- 点击测试：320 下依次点击 8 个页签，每次点击后 100ms 断言 active 可见；只做初始渲染会在用户点第二个页签后再次失效。
- `hashchange` 测试：直接改 `location.hash`，断言 active 可见。
- 截图：`shots/P5/`，320 下点击前后各一张。
- 5A 的验收必须在**上游合并后的主题版本**上跑；在本地改主题 CSS 不算通过。
- 5B 的验收在四仓当前版本上跑，并记录主题版本号；5A 合并后删除 5B，再跑一次确认无双重滚动。

### 7.4 风险与回滚

- 5B 必须幂等：模块级 `installed` 标志，避免 8 个 view 各挂一次监听。
- 5B 必须处理点击与 `hashchange`，只处理初始渲染等于没修完整。
- 5B 与 P1/P2 改同一批 view 文件，**必须在 P1/P2 之后**，否则并行的人会互相踩。
- 回滚：删除 helper 与各 view 的调用；若 5A 已合并，先删 5B 再验收，避免双重滚动。

### 7.5 5B 参考实现（约 15 行，单仓一份）

```js
var installed = false;
function reveal() {
  var ul = document.querySelector('#tabmenu ul.tabs');
  var li = ul && ul.querySelector('li.active');
  if (li) li.scrollIntoView({ inline: 'nearest', block: 'nearest' });
}
return function installRevealTab() {
  if (installed) return;
  installed = true;
  requestAnimationFrame(reveal);
  document.addEventListener('click', function(ev) {
    if (ev.target.closest('#tabmenu')) setTimeout(reveal, 0);
  });
  window.addEventListener('hashchange', reveal);
};
```

本次实测：320 下 NGINX logs 页 `scrollLeft` 初始 0、active 不可见；执行 `scrollIntoView({inline:'nearest'})` 后 `scrollLeft=494`、active 可见。机制成立。

---

## 8. P6（可选，且必须先满足主题契约）

### 8.1 前提（不满足就不做）

P1/P2/P4/P7 已合并并稳定一个版本，**并且**满足以下任一条件：

1. Aurora 主题把窄屏堆叠契约从 `<768` 上移到 `≤1024`（UPNP 为 900），或
2. 产品明确接受 768–1024 用表格，且 P1 的验收证明该区间最窄列不再出现 30px。

**为什么**：P1/P2 的自定义堆叠覆盖到 1024/900，而 Aurora 原生只在 `<768` 堆叠。P6 若直接删除自定义 CSS，768–1024 会回到实测的 `[76,87,30,52,155,239]`（Size 30px），把 P1 修好的缺陷原样带回来。这不是“收敛”，是回退。

### 8.2 内容

1. **收敛（条件项）**：删除 NGINX/UPNP/CF 的自定义堆叠 CSS，只保留 `data-title`，交给主题。仅当 8.1 的条件成立。
2. **暗色板清理（独立项，可单独交付）**：删除 NGINX 的 166 个硬编码暗色色值，改用主题变量；不与收敛同提交。
3. **断点白名单**：`480 / 600 / 768 / 1024`，禁止再出现 560/720/760/900 混用。900 若保留，必须写明是 UPNP 的表格契约而不是随手值。
4. **kv 表不删**：`.nm-kv-table`/`.ubr-kv-table` 的标签在 `th` 里，Aurora 的 `td::before{content:attr(data-title)}` 契约覆盖不到；删掉它们的自定义规则会让 320 下 `tr=flex`、`th`/`td` 127/127 并排的缺陷回归。除非先把 kv 表改成 `td[data-title]` 结构，否则保留。

### 8.3 与 P1/P2 的关系（更正）

- P6 会**删除** P1/P2 加的 `#maincontent` 堆叠块；这是覆盖，不是回滚。
- P6 合入后，P1/P2 的 CSS 部分不再可单独 revert：回滚单元变成 P6。必须按 1.5 的逆序处理。
- 若 8.1 条件不满足，**P6 的收敛项撤销**，只保留 8.2 的暗色板清理与断点白名单。

### 8.4 验收与回滚

- 收敛项：320/390/480/640/767 由主题堆叠，标签来自 `data-title`；**768/820/900/1024 必须仍然通过 P1 的“最窄列 ≥60、无 <40”断言**；1280+ 正常表格。
- 暗色项：明暗截图对比；`grep` 统计非 fallback 的硬编码色值数量降到 0。
- 风险：原生窄屏是“标签在上、两列一行”，与 P1/P2 的“标签在左”不同，属于可见改版，需要 UI 确认。
- 回滚：按仓库拆 4 个提交，逆序 revert；P6 的收敛项与暗色项分开提交。

---

## 9. P7：PM `select` 超出字段 3px

### 9.1 证据

- PM settings，320 下实测：`select` 宽 210px、`.cbi-value-field` 宽 207px，`select.right - field.right = 3px`。
- 根因在主题：Aurora `select{max-width:100%;min-width:calc(var(--spacing)*52.5)}`，`--spacing=4px` 时 `min-width=210px`。CSS 中 `min-width > max-width` 时 `min-width` 胜，所以 `max-width:100%` 救不了。
- 页面级横滚仍为 0，所以这是控件内部溢出，不是页面级破版；优先级低于 P1/P2/P4。

### 9.2 改法

```css
/* performance-manager/ui.css，只作用于表单字段内的 select */
#maincontent .cbi-value-field select { min-width: 0; }
```

实测：加规则后 `select=207`、`field=207`、溢出 0。

- 若其他仓库也有同样实测（当前只有 PM 有数据），复制同一条规则到对应 CSS；没有实测就不要先加。
- 不覆盖下拉展开面板：原生 `<select>` 的弹出层宽度由浏览器控制，`min-width:0` 只修闭合态。展开态仍归 U5。

### 9.3 验收

- 320/390/480：`select.right - field.right ≤ 0.5px`；页面横滚 `=0`。
- 打开下拉、选最长选项后，闭合态仍不超出字段；展开面板若超出视口，记录到 U5，不在本批声称修复。
- 明暗各一次；截图 `shots/P7/320-before/after`。

### 9.4 风险与回滚

- 风险：`#maincontent .cbi-value-field select` 会影响该仓所有表单 select；当前只有 PM 加，范围可控。
- 顺序：与 P4 同改 `ui.css`，**P4 先、P7 后**；若 P4 未合入，P7 可单独先做。
- 回滚：单提交 `git revert`；若 P4 之后改了相邻行，按 1.5 逆序先 revert P7。

---

## 10. 风险登记（跨批）

| 编号 | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R1 | 未验证项被当作结论 | 改错方向 | 报告与方案均保留「未验证」标签；P0 门禁 |
| R2 | 768–1024 由表格变长卡片 | 页面变长、滚动增加 | PR 附前后截图，接受后再合 |
| R3 | 属性改名漏改 | 个别列标签为空 | 1.6 静态守卫 + 逐 `td` 断言非空 |
| R4 | 只加倍 class、不写 `display`/`flex` | 768–1024 标签仍隐藏 | 必须用 `#maincontent` 前缀 + `display:block` + `flex:0 0 100%`；已实测 A 写法失败 |
| R5 | PM 方案 B 只改一半（加 `data-title` 不去 `min-width`） | 堆叠无效，仍在 576px 画布内 | 两处绑定同一提交 + `@container` 断言 |
| R6 | bootstrap 结论外推 | 其他主题上翻车 | U2 完成前禁止声称兼容 |
| R7 | 主题修复等待过久 | 窄屏体验长期不改善 | 5B 兜底可开关，上游合并后移除 |
| R8 | PM 桌面仍有 79px 横滑 | 大屏体验差 | P4-A 卡片跨列；1920 纳入必测 |
| R9 | kv 表被 P6 顺手删规则 | 320 下 th/td 并排回归 | 8.2 第 4 条；P1/P2 单独验收 kv 表 |
| R10 | 主题升级改变 48rem 契约 | P1/P2 的 1024/900 断点失效 | 1.6 主题契约探针先失败；重新审计 |
| R11 | P6 在主题未上移契约时执行 | 768–1024 Size 30px 回归 | 8.1 门禁；不满足则撤销收敛项 |
| R12 | `select` 展开面板仍超宽 | 闭合态修好但展开态仍溢出 | 9.2 明确不覆盖；U5 单独处理 |

# 方案自审

## A. 自审发现（挑刺视角）

### A1. 未验证的假设

- 原文默认“UPNP 与 NGINX 同构 → 一定同样坏”。这是**推断**，不是观测。已改为：P2 验收必须自测（数据行或合成行），不得引用 NGINX 结果。
- 原文默认“CF 堆叠在真实页面成立”。实际 CF 成功路径依赖 `source-registry` RPC，本次只渲染了错误态，真实表从未出现。已降级为“合成 DOM 契约成立 + 真实行未验证”。
- 原文默认“PM 表格只是横滑，没问题”。PM 表体无数据，行内行为完全没看过。已把 P4-B（堆叠）设为强依赖 U1；P4-A（卡片跨列）不依赖 U1，因为横滑根因是 497px 容器对 576px 表格，已实测。

### A2. 会牵连 JS 依赖的 class 或属性

- `data-label` → `data-title`：已 grep 全仓，**没有 JS 读取 `data-label`**（`dataset.label`、`getAttribute('data-label')`、`[data-label]` 均无命中，除两个无关项目的 chart.js）。
- 但**验收探针**依赖 `data-label`（`synth.js`/`pseudo*.js`）；实施时必须同步改探针，否则会误判“属性丢了”。
- CF 的折叠逻辑依赖 `data-cfi-fold` 与 `li[display]`，与 `data-label` 无关，改名不影响。
- NGINX `nm-actions::before`、`td[colspan]::before` 依赖伪元素存在；加倍选择器后仍存在，但 `colspan` 行要单独确认。

### A3. 阶段顺序的隐藏依赖

- 原稿把 P1 写成“只提特异性”，但只提特异性时标签仍是空字符串（`attr(data-label)` 被 Aurora 的 `attr(data-title)` 顶掉）。**两件事必须同批**，已合并。
- P6 与 P1/P2 互斥：P6 删除自定义堆叠，会把 P1/P2 的特异性补丁一起删掉。原稿没有说明，容易被理解成“回退”。并且会把 768–1024 的 Size 30px 缺陷带回来。第二轮已改为 8.1 门禁：主题契约未上移到 1024/900 就撤销收敛项。
- P3 的“删除重复媒体查询”前提不成立：容器查询已生效（`utils.js:579-581`），不存在“启用”步骤；第二轮已撤销 P3，只保留可选去重。

### A4. 验不了的验证项

- bootstrap（U2）：在 harness 修好前无法验收。**标 BLOCKED，不得写“通过”**。
- 原生下拉展开态（U5）：展开面板动态生成，部分页面无选项；只能测“能否展开 + 是否超出视口”，不能测全部交互。
- 微信/WebView 内置浏览器：完全无法在本环境模拟，方案里不承诺。
- 主题修复（P5-5A）：验收只能在用户实际主题版本上做，四仓 CI 无法覆盖。

### A5. 会临时变丑或功能回退的地方

- P1/P2 后，768–1024 从“挤扁的表格”变成“竖向长卡片”，页面明显变长——功能变好，观感变“重”。
- P4 方案 B 同理，Rill 页会变长；`colspan` 空态行若处理不好会出现空标签。
- P6 若执行，会把 768–1024 的卡片改回表格（Size 30px 回归）；只有主题契约上移后才允许，见 8.1。
- P5 兜底若与主题后续自带滚动叠加，会出现“滚两下”的跳动。

### A6. 其他

- 截图基线必须固定容器、字体、`prefers-reduced-motion`，否则高度比较没有意义。
- NGINX 的 166 个暗色色值属于“未爆的雷”，但**不属于响应式范围**；第二轮把它拆成 P6 的独立提交（8.2 第 2 条），不与收敛项同批。
- 四仓改动量差异大（NGINX 27 处 vs PM 0 处），不能用统一工时评估，方案按“单仓可独立回滚”设计。

## B. 自审前后改了什么（首轮；其中第 1、4、7、9 条已被 D 覆盖）

> 本节是首轮自审的记录。第二轮拿数据集与主题源码复核后，第 1 条（“特异性加倍”）、第 4 条（P4 依赖 U1）、第 7 条（14 档/阈值）、第 9 条（启用容器查询）已有更正，**以 D 为准**；保留本节是为了看修订轨迹。

| # | 自审前 | 自审后（定稿） | 原因 |
|---|---|---|---|
| 1 | P1 只提 CSS 特异性 | P1 = 属性改名 + 特异性处理（首轮写法为“加倍”） | 只做一半仍坏；第二轮已改为 `#maincontent` 前缀 |
| 2 | P2 验收引用 NGINX 实测 | P2 必须自测（真实行或合成行） | 未验证不能传导 |
| 3 | 未单列补测批次 | 新增 P0（U1–U5）与门禁 | U1 阻塞 P4，U2 阻塞一切“兼容 bootstrap”声明 |
| 4 | P4 直接给堆叠方案 | P4 先决策 A/B，强依赖 U1；B 方案两处改动绑定 | PM 表体无数据，不能拍脑袋 |
| 5 | P6 与前序批次关系不明 | P6 标可选，并明确会覆盖 P1/P2 补丁，二选一 | 避免被误解为回退 |
| 6 | bootstrap 未标注 | 验收标 BLOCKED | 验不了就不能说通过 |
| 7 | 只有“跑一下断点”的口头验收 | 每批固定档位 + 阈值表 + 截图命名 + 回滚命令（第二轮改为 16+5 档） | 可执行、可复核 |
| 8 | 未提属性改名对探针的影响 | 明确列出需同步修改的探针文件 | 否则验收自己会误判 |
| 9 | 未提启用容器查询的行为变化 | R4：首批只启用不删除，观察宽屏+侧栏 | 防止视觉突变 |
| 10 | 批次“建议顺序”未说明独立性 | 0 节表格明确每批可独立交付、无“全做完”门禁 | 满足分批落地要求 |

---

## C. 每批交付物清单（可直接当 PR 模板）

- [ ] 代码改动（单仓单提交，提交信息注明批次号）
- [ ] before/after 截图（320/640/768/1024/1280/1920 × 明暗）
- [ ] 验收表：16+5 档 × 1.2 的可测指标，逐项打勾
- [ ] `node assert.js <repo> ...` 退出码 0 的日志（不是口头“看起来正常”）
- [ ] 未验证项声明（若有；P2 必须注明“合成行”还是“真实行”）
- [ ] 回滚命令与逆序说明（`git revert <sha>`；P6 合入后不得单 revert P1/P2）
- [ ] 若涉及属性改名：探针同步修改记录
- [ ] 记录主题版本（Aurora 1.2.0）与 48rem 契约探针结果
- [ ] 若改 `ui.css`：P4/P7 的先后顺序已在提交信息里注明

---

## D. 第二轮自审（本轮：拿方案打数据集与主题源码）

### D1. 被推翻的结论

| # | 原结论 | 推翻依据 | 改成什么 |
|---|---|---|---|
| 1 | CF 的 `@container` 是死代码，需要“启用” | `utils.js:579-581` 的 `appendFooter` 已给 `.cbi-map` 补 `cfi-form-map`；`cloudflare-ip.css:525-527` 据此设置 `container-type:inline-size` | P3 撤销“启用”目标，只保留可选的等价去重 |
| 2 | 选择器加倍后特异性 `(0,1,3)/(0,1,2)` 高于 Aurora，足以压住 | Aurora 实际是 `td` `(0,2,1)`、`td::before` `(0,2,2)`；加倍得到同样数值，只是平手；实测插件 CSS 索引 2、Aurora 索引 0，靠顺序才赢 | 改用 `#maincontent` 前缀 `(1,1,1)/(1,1,2)`；并补 `display:block`、`flex:0 0 100%`、`margin-bottom:0` |
| 3 | 按 P1 原稿（只加倍 + 改 `content`）就能修好 | 浏览器实测：768/1024 下 `td::before` 仍是 `display:none`、宽 0；320 下 `flex-basis` 仍是 `50%` | 原稿写法判定为**无效**；P1/P2 补三处复位 |
| 4 | PM “1280 起不再横滑” | fresh load 实测 1280/1440/1920 的 wrap 都是 497px，表格 `min-width` 576px，恒有 79px 横滑 | P4 范围改为全宽度；默认方案改为 ≥1024 卡片跨列 |
| 5 | P6 只是“收敛”，不会回退 | Aurora 原生只在 `<768` 堆叠；P1/UPNP 自定义到 1024/900。删掉自定义 CSS 后 768–1024 回到 `[76,87,30,52,155,239]`，Size 30px 回归 | P6 加 8.1 门禁；主题契约未上移就撤销收敛项 |
| 6 | P2 与 NGINX“同构所以同样坏”只是推断 | 用合成 `<tr>` 实测：320 `tr=flex/td=block/basis 50%/content=""`，768–900 `td=table-cell/::before none` | 保留“真实行未验证（U4）”，但 CSS 契约已实测；P2 可先做 CSS |

### D2. 阈值改动（每条给测量值）

| 原阈值 | 新阈值 | 依据 |
|---|---|---|
| 最窄可见列 `≥120px` | `≥60px` 且无 `width<40` | 1025 实测 67、1280 实测 84；缺陷列 30。原阈值会把正常态判失败 |
| 行高 `190–230px` | `rowH - ΣtdH ≤ 32` | 修后 320 行高 329、768 行高 230；原区间在 320 必失败 |
| 标签宽 `80–90px` | `abs(width - 7.2*fontSize) ≤ 2` 且 `60–120px` | 修后 320=86、768=98；预修复 768=0 |
| `scrollLeft > 0` | 只判 active 可见（±1px） | 首个页签 `scrollLeft=0` 也是正确状态 |
| 控制台 error `=0` | 只允许基线已有 2 条 `"%s/%s.js%s".format`，新增 `=0` | 当前 1088 次测量基线固定有 2 条，不设 allowlist 会永远失败 |
| 14 档 | 16 档（+414、+1920）+ 5 缩放 | 1920 才能暴露 PM 的 79px 横滑；414 是常见手机宽度 |
| 标签内容“不得为 `""`” | 不得为 `none`/`""`，且等于列名 | `getComputedStyle` 对 `display:none` 的伪元素返回 `none` |
| 只判 `td=flex` | 增加 `flexBasis=100%`、`::before display=block` | 预修复 `td=flex` 但 basis 50%，值区仍被挤 |
| 无 `select` 指标 | `select.right - field.right ≤ 0.5` | 320 实测 3px；加 `min-width:0` 后 0 |
| PM 只看页面横滚 | A：≥1024 `wrap` 溢出 0；B：全部 0 | 1920 wrap 79px，页面横滚却是 0，只测页面会漏 |

### D3. 批次顺序调整

1. **撤销 P3**（容器查询已生效），编号保留但标“撤销”，不再占交付顺序。
2. **新增 P7**（`select` 3px），排在 P4 之后（同改 `ui.css`）。
3. **P5B 移到 P1/P2 之后**：P5B 与 P1/P2 改同一批 view 文件，先做会被后做的覆盖。
4. **P6 移到 P1/P2/P4/P7 之后**，并加 8.1 门禁；主题契约未上移就撤销收敛项。
5. **P0 基线必须在任何代码批次合入前留档**：否则 P1 修完再测，基线被污染。
6. **P4-A → P4-B 串行**：B 的容器查询依赖 A 的宽容器；B 是 A 的增量，不可并行。
7. **回滚逆序**：`P6 → P7 → P5B → P4-B → P4-A → P2 → P1`；P6 合入后 P1/P2 不再单独可 revert。

### D4. 补的缺失项

| 缺失项 | 补到哪 | 依据 |
|---|---|---|
| `select` 比容器宽 3px 没有归属 | P7 | 320 PM settings 210 vs 207 |
| PM 768–1024 内容列 278px 只在报告里，方案 P4 范围写的是 ≤600 | P4 全宽度 + 1920 | wrap 278（768）/497（1920） |
| NGINX files 空目录 `td[colspan=6]` 没有 `::before` 规则 | P1 | `files.js` 空态行；不加会在空态多出 7.2em 空标签位 |
| NGINX/UPNP kv 表 320 下 `tr=flex`、th/td 127/127 并排 | P1/P2 | 本轮实测（两仓 overview） |
| 每批“修完怎么防止改回去”没有可跑机制 | 1.6 + 每批 checklist | `assert.js` 已跑通，基线 `EXIT=1` |
| 单批 `git revert` 在 P6 后会冲突 | 1.5 逆序 + 冲突矩阵 | P6 与 P1/P2 同 hunk |
| P5 只做初始滚动，点击后再次失效 | 7.3/7.5 | 点击与 `hashchange` 都要处理 |
| P4 只有“U1 阻塞”没有退路 | 6.4 五条退路 | U1 失败/真实行溢出/空态/UI 拒绝/`:has` 不支持 |
| 主题升级会改变断点契约 | 1.6 契约探针 + R10 | Aurora 48rem 是硬编码 |
| kv 表若被 P6 删除会回归 | 8.2 第 4 条 + R9 | 主题契约只覆盖 `td`，不覆盖 `th` |

### D5. 仍然未验证（保持标签）

- U1 PM 真实数据行：P4-B 仍以 U1 为门禁；P4-A 不受影响。
- U2 bootstrap：未测；不得声称兼容。
- U3 长路径：未测；P1/P2 的 `word-break` 只按现有最长文本验收。
- U4 CF/UPNP 真实数据行：P2 只用合成行验证了 CSS，真实行仍归 U4。
- U5 下拉展开态：P7 只修闭合态 3px；展开面板宽度仍不可判定。
- 5A 主题上游排期：未知；5B 是兜底，不是承诺。
