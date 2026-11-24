# 四仓「原生为主 + 响应式回原生」主方案

- 日期：2026-11-12
- 状态：**唯一有效方案**。取代以下两份文档的实施部分，旧文档保留作历史：
  - `luci-responsive-refactor-plan-2026-11-11.md`（按缺陷分批 P0–P7，依赖 `#maincontent` 前缀 + 显式复位）
  - `luci-responsive-breakpoint-audit-2026-11-11.md`（测量数据仍有效，但第 7 节的优先级映射作废）
- 基础事实来源：`luci-native-style-audit-2026-11-10.md`（变量/class 契约）、`luci-responsive-breakpoint-audit-2026-11-11.md`（1088 次测量）
- 路线：**① 回到原生为主，响应式也回原生**。插件不自带视觉外壳，不为某个主题写特异性补丁。
- 约束：本文件只描述未来实施动作。当前会话只读，未改四仓代码。

---

## 0. 路线决定与作废清单

### 0.1 一句话

四仓的自定义 CSS 从 **2461 行压到 ≤680 行**（逐段核算 672 行）；所有表格/表单/按钮/徽标/提示回到原生 class；所有 `@media`/`@container` 重排删除，窄屏交给主题的 `data-title` 契约；主题在 768–1024 的缺陷**不在插件侧绕过**，只做结构规避或提上游。

### 0.2 作废条目（逐条给理由与证据）

| # | 作废手法 | 为什么作废 | 证据 |
|---|---|---|---|
| X1 | `#maincontent` 前缀提高特异性 | 原生审计 §7.3 明确禁止把布局 id 当样式选择器；它只为压过 Aurora 而存在，换主题/换 DOM 结构即失效；且把插件绑死在“主题有 `#maincontent` 且内部结构不变”上 | `luci-native-style-audit-2026-11-10.md` §7.3；响应式方案 §3.3 |
| X2 | 选择器加倍（`.nm-responsive-table.nm-responsive-table td`）——旧方案评估过、实测后**未采用**的 A 备选 | 加倍后是 `(0,2,1)`，与 Aurora `td` **平手**，不是胜出；实际靠 stylesheet 顺序（插件索引 2、Aurora 索引 0）才赢，换主题或加载顺序就翻。旧方案 L276–292 已把 A 写法判为“**无效**”，最终采用 B（`#maincontent` 前缀 + 显式复位）；本方案连 B 也作废（见 X1），故加倍更不得使用 | 旧方案 §3.3 实测：A 写法在 768/1024 下 `::before display:none`、宽 0；320 下 `flex-basis:50%` |
| X3 | `data-label` + `content:attr(data-label)` | 两个主题只读 `data-title`；插件规则赢不了时，Aurora 基础 `td::before{display:none}` `(0,2,2)` 仍在，窄屏就出现“空标签占位、值被挤” | NGINX 320 实测：`content=""`、标签宽 118px、6 个 td 各 126px；`data-label` JS 计数 CF 11 / UPNP 16 / NGINX 27 / PM 0 |
| X4 | 自定义 `@media`/`@container` 重排表格 | 断点与主题 768 不对齐（插件 1024/900/600），制造 768–1024 死区；四仓四种结果；且同一批 CSS 被多批次反复改，回滚必冲突 | NGINX 768：列宽 `[76,87,30,52,155,239]`，Size 恒 30px；UPNP 900 断点、CF 600/900 双套、PM 560/600/720/760/768/900 |
| X5 | 自建暗色检测（`body.nm-dark`/`nm-light`、`prefers-color-scheme`、`detectLightMode()`）——**代码事实**，旧方案未主张此法（旧方案 P6 只计划清理硬编码暗色） | 主题的标准开关是 `[data-darkmode="true"]`，两套开关会错位；NGINX 为此维护 4 套调色板、166 个硬编码色值 | NGINX CSS 190/208–224/757/897/1010/1107；`utils.js:12,55-57,734` |
| X6 | 自建布局壳（`.pm-shell`、`.pm-card-grid`、`.pm-table-wrap`、`.nm-file-table-wrap`、`.cfi-table-wrap`、`.ubr-table-wrap`） | 与主题的 2 列表单叠加后列宽失控；`min-width:36rem` 让表格在全宽度都横滑 | PM wrap 实测 1920 `497/576`（恒 79px）；768 `278/576`；NGINX 文件表同时 `min-width:760px` + 堆叠媒体查询，两套意图互斥 |
| X7 | 单主题 class（`cbi-input-select`、`pre.errors`、`cbi-button-neutral`、`cbi-map-title`） | 只在 Aurora 或只在 bootstrap 有定义；`cbi-map-title` 两主题都不存在 | `cbi-input-select` 使用点：UPNP 5、CF 1、PM 3、NGINX 12；审计 §3 |
| X8 | `.ys-tool-footer` 品牌页脚 | 四仓复制同一段硬编码 `#2f7df6` + `rgba()`，合计 **289 行**（UPNP 70 + CF 64 + PM 84 + NGINX 71），不含散落在各 `@media` 里的 footer 规则；不属于 CBI 契约 | 各 CSS 行段见第 4 节 |

### 0.3 保留的旧结论（不推翻）

- 页面级横向滚动 1088 次全为 0；按钮最小高 ≥32px、`tiny=0`；`.cbi-value` 在 ≤683 堆叠、≥768 并排；卡片同行高度差恒 0。这些是原生行为，改造不得引入回归。
- 未验证项 U1–U5 与 bootstrap 结论继续保留「未验证」标签，不得写成缺陷。

---

## 1. 「原生」的可执行定义

判定原则：**能用 grep 判死的才算定义**。以下每条都给出命令或 DOM 判据，不接受“看起来原生”。

### 1.1 HTML / DOM 白名单

只允许生成下表中的结构。出处均为 LuCI 25.12 的 `form.js` / `ui.js` / 主题 CSS 已有契约。

| 用途 | 允许的结构 | 原生出处 |
|---|---|---|
| 页面标题 | `.cbi-map` + `h2[name="content"]` + `.cbi-map-descr` | `form.Map` |
| 区块/卡片 | `.cbi-section` + `h3` + `.cbi-section-descr` + `.cbi-section-node` | `form.AbstractSection` |
| 键值行 | `.cbi-value` + `.cbi-value-title` + `.cbi-value-field` + `.cbi-value-description` | `form.NamedSection` |
| 表格 | `<table class="table">` + `thead/tr/th/td`，每个 `td` 带 **`data-title`**；或 `.cbi-section-table` + `-titles/-row` | `ui.Table` 写 `data-title`，两主题都读 |
| 按钮 | `.cbi-button` + `-positive/-negative/-action/-apply/-reset/-add/-remove/-edit/-reload` | 主题 CSS + `cbi.js` |
| 状态徽标 | `.label` + `.success/.warning/.notice/.important` | `admin/status/overview`、`admin/system/system` |
| 提示块 | `.alert-message` + `.info/.success/.warning/.danger/.error` | `admin/network/network`、`system/reboot` |
| 内页标签 | `s.tab()` / `ui.tabs` 生成的 `ul.tabs > li > a`；`cbi-tabmenu` 不是独立组件，不手写 | `system/startup`、`status/routes` |
| 动态列表/下拉 | `form.DynamicList` / `form.ListValue` / `form.MultiValue` | `form.js`、`cbi.js` |
| 暗色 | 只读 `[data-darkmode="true"]`，不自己加 `body` class | 两主题 |
| 页面操作区 | `.cbi-page-actions` / `.cbi-section-actions` | `luci.js`、`form.js` |

**禁止生成的 DOM**：

| 禁止 | grep 判据 | 期望 |
|---|---|---|
| `data-label` | `grep -rn "data-label" --include='*.js' --include='*.css'` | 0（测试夹具除外） |
| `cbi-map-title` | `grep -rn "cbi-map-title"` | 0 |
| 手写 div 表格 | `grep -rnE "'class': 'table'|class=\"table\""` 后人工确认无 `div.tr/div.td` 结构；或 `grep -rn "table-titles"` | 0 |
| 自建状态横幅 | `grep -rnE "status-banner|nm-status|cfi-status"` | 0（改用 `.alert-message`） |
| 自建徽标 | `grep -rnE "nm-badge|cfi-badge|ubr-badge|pm-badge"` | 0（改用 `.label`） |
| 内联样式 | `grep -rnE "style: ?['\"]" --include='*.js'` | 0（除动态 `width/height`，需在例外表登记） |
| 单主题 class | `grep -rnE "cbi-input-select|pre\\.errors|cbi-button-neutral"` | 0 |

### 1.2 CSS 白名单

**允许的属性**（与主题无关，改主题不变形）：

- 布局：`display`、`flex`/`grid` 及其子属性、`gap`、`order`、`overflow`、`box-sizing`、`width/max-width/min-width`（仅结构容器，且不得写死大于 `100%` 的值）
- 排版：`font-family: var(--font-mono)`、`font-size`（`em`/`%`/`rem`）、`font-weight`、`line-height`、`white-space`、`word-break`、`overflow-wrap`、`text-align`
- 盒模型：`padding`、`margin`、`border`（不写颜色时默认 `currentColor`）、`border-radius`、`max-height`
- 颜色：**只允许 `currentColor`、`inherit`、`transparent`**

**允许的变量只有两个**：`--font-sans`、`--font-mono`。

**禁止的 CSS**：

| 禁止项 | grep 判据 | 期望 |
|---|---|---|
| 颜色字面量 | `grep -nE '#[0-9a-fA-F]{3,8}\\b\|rgba?\\(\|hsla?\\(' <css>` | 仅 `/* editor-palette:begin */ … /* editor-palette:end */` 标记区间内允许（例外 E6），其余 0；**例外 E20 的 bootstrap 兼容层**同样允许，但必须以 `body.ubr-theme-bootstrap` 开头且每条注明对比度 |
| 非白名单变量 | `grep -oE 'var\\(--[a-z0-9-]+' <css> \| sort -u` | 输出只能是 `var(--font-sans` / `var(--font-mono` |
| `#maincontent` 选择器 | `grep -n '#maincontent' <css>` | 0 |
| `data-label` | `grep -n 'data-label' <css>` | 0 |
| 响应式重排 | `grep -n '@media\|@container' <css>` | 只允许 `@media (prefers-reduced-motion: reduce)`；**例外 E20** 的 `≤600px`（按钮换行）与 `≤700px`（stats 两列）两条，且块内选择器必须带 `body.ubr-theme-bootstrap`（stats 网格本身是插件自有组件，不受此限） |
| 自建暗色 | `grep -nE 'nm-dark\|nm-light\|prefers-color-scheme\|detectLightMode'` | 0 |
| 布局类前缀 | `grep -nE '\\.(nm\|cfi\|pm\|ubr)-[a-z-]+' <css>` | 每条命中必须出现在第 3 节例外表 |
| `!important` | 先剔除 `@media (prefers-reduced-motion: reduce)` 块，再 `grep -n '!important'` | 0（仅该无障碍块内允许） |
| 单主题 class | `grep -nE 'cbi-input-select\|pre\\.errors\|cbi-button-neutral\|cbi-map-title'` | 0 |

**允许一个仓一个 CSS 文件**；不得新增第二个样式表。若某仓改造后剩余为 0，直接删文件并从 view 的 `require`/`render` 中移除引用。

### 1.3 例外申请格式

任何不满足 1.1/1.2 的写法，必须写进第 3 节例外表，格式：

```
类名 | JS 依赖点（文件:行 数量） | 为什么不能删 | CSS 行数上限 | 撤销条件
```

未登记的命中一律视为失败，CI 脚本按 1.2 的 grep 判据直接退出非 0。

---

## 2. 响应式回原生

### 2.1 删除清单（按实际行段，已核对仓库）

| 仓库 | 要删的响应式块 | 行数 | 说明 |
|---|---|---|---|
| UPNP | `upnp-nat-relay.css` 305–351 | 47 | `@media (max-width:600px)`，缩字号/改网格 |
| UPNP | `upnp-nat-relay.css` 352–430 | 79 | `@media (max-width:900px)` 表格堆叠 + `attr(data-label)` |
| CF | `cloudflare-ip.css` 378–416 | 39 | `@media (max-width:600px)` |
| CF | `cloudflare-ip.css` 418–519 | 102 | `@media (max-width:900px)` 表格/div 表格堆叠 |
| CF | `cloudflare-ip.css` 525–629 | 105 | `@supports(container-type)` + `@container 600/900` |
| CF | `cloudflare-ip.css` 369–376 | 8 | `#tabmenu` focus 覆盖（主题职责） |
| PM | `ui.css` 160–190 | 31 | `760/900/768/560` 四段网格与字号 |
| PM | `ui.css` 266–275 | 10 | footer 的 `max-width:600` |
| NGINX | `nginx-manager.css` 88–97 | 10 | `.nm-responsive-table` 基础块 |
| NGINX | `nginx-manager.css` 423–501 | 79 | `@media (max-width:1024px)` 表格堆叠 |
| NGINX | `nginx-manager.css` 503–520 | 18 | footer 的 `max-width:600` |
| NGINX | `nginx-manager.css` 1042–1099 | 58 | 文件表 1024 断点（路径行/行底色） |
| NGINX | `nginx-manager.css` 1101–1105 | 5 | 编辑器 textarea 高度（改无条件 `min-height:260px`） |
| NGINX | `nginx-manager.css` 1107–1122 | 16 | `prefers-color-scheme` + 1024 行底色 |

合计删除 **607 行**响应式代码。删完后四仓 CSS 里除 `prefers-reduced-motion` 外不应再有 `@media`/`@container`。

> 行段核对更正：2026-11-10 审计把 UPNP footer 记为 235–352，与 `@media 600` 的 305–351 重叠；实际 footer 到 304 结束（70 行）。本方案以文件实际行号为准。
>
> CF 的 `@container` **不是死代码**：`utils.js:579-581` 的 `appendFooter` 已给 `.cbi-map` 补 `cfi-form-map`，`cloudflare-ip.css:525-527` 因此正常路径就设了 `container-type:inline-size`。本方案删除它的理由不是“无效”，而是它与 141 行的两套 `@media` 重复表达同一个重排、且把布局决策留在插件侧；删掉后由主题契约承担。

### 2.2 删完后靠什么工作

| 能力 | 由谁提供 | 插件要做什么 |
|---|---|---|
| ≤767 表格堆叠 | Aurora `@media not all and (min-width:48rem)`：`tr{display:flex;flex-wrap:wrap}`、`td{flex:50%}`、`td::before{content:attr(data-title);display:block}` | 每个 `td` 写 `data-title`；保留 `<thead>`（主题负责隐藏）；不写任何堆叠 CSS |
| 表单行堆叠 | 主题 `.cbi-value` 在 ≤683 堆叠 | 用 `.cbi-value`，不自建 `.pm-field`/`.nm-inline-setting` |
| 页面宽度 | `#maincontent` 自带 `max-width` 与内边距 | 删 `.pm-shell` 等居中容器 |
| 表格横滑 | 主题 `.table` 的容器行为 | 删 `.pm-table-wrap`/`.cfi-table-wrap`/`.ubr-table-wrap` 的 `overflow-x` 与 `min-width` |

**验收判据（可测）**：

- 360 宽：每个 `td` 的 `getComputedStyle(td,'::before').content` 等于对应 `th` 文本（含引号），且 `display=block`；`tr` 的 `display=flex`；`td` 的 `flexBasis=50%`（主题行为，允许 50%，不再要求 100%）。
- 768/1280：`tr=table-row`、`td=table-cell`、`::before display=none`；所有可见 `td` 宽 ≥60px 且无 `<40px`。
- 320/360/390/480/640/768/1024/1280/1920：`documentElement.scrollWidth - clientWidth = 0`。

### 2.3 主题 768–1024 的已知缺陷：不许插件补丁，只做这五种处理

按 ① 的路线，插件侧**不得**写 `#maincontent` 前缀、不得加倍选择器、不得自建断点。可选做法与代价如下，逐项给本次决策。

| 做法 | 代价 | 适用 | 本次决策 |
|---|---|---|---|
| A. 调整表格列数与内容结构（合并列、列内两行、操作列图标化） | 改 JS 渲染与 `data-title`，失去被合并列的独立排序；页面信息层级变化 | 列多、单列内容短（NGINX 文件表、权限表） | **首选** |
| B. 改成非表格布局（每行 `.cbi-value` 或两行卡片） | 失去表头排序与列对齐；markup 增加；操作按钮重排 | 行数少、字段固定（kv 表、PM 历史） | **用于 kv 表与 PM 明细** |
| C. 换原生组件（`cbi-input-select` → 原生 `select`；自建分段器 → `form.ListValue`/radio） | 交互形态变化（下拉替代分段按钮、radio 占纵向空间）；需同步 JS | 表单控件 | **执行**（跨主题正确性优先） |
| D. 缩短列名/文案 | 只缓解、不解决；列宽由内容决定时收益有限 | 表头文字过长 | **辅助**，不单独作为方案 |
| E. 向主题上游提交 | 排期不可控；但一次修好全部插件与原生页 | 主题层缺陷（页签滚动、select min-width、堆叠上界） | **并行提交，不作为交付依赖** |

#### 逐缺陷决策

**D1. NGINX 768–1024 六列挤压，Size 30px**

- 根因：768 下表格可用宽约 704px，6 列内容宽合计 639px 仍按内容分配，`Size` 只有 30px；不是特异性问题，是列数问题。
- 决策 **A**：`files` 表 6 列 → 4 列。
  - `Name` 列内两行：文件名 + 类型/权限副行（`<br><small>`，无自定义 class）。
  - 删除独立 `Type` 列与 `Permissions` 列（内容并入副行）。
  - `Actions` 改为图标按钮（`.cbi-button` + `title`），文本标签保留在 `aria-label`。
  - `Size`、`Modified` 保留。
- 验收：768 下四个 `td` 宽度均 ≥60px，`Size` ≥60px；320 下主题堆叠、四个标签均非空。
- 若 4 列在 768 仍 <60（例如文件名过长），退到 **B**：`files` 改为每行一个 `.cbi-value`（名称+副行），不使用表格。

**D2. PM 768–1024 内容列缩到 278px**

- 根因：PM 自建 `.pm-card-grid--primary` 在 ≥900 变两列（`minmax(0,1.25fr) minmax(18rem,.75fr)`），叠加主题在 768–1024 的双列表单，右侧卡片内容列只剩 278–387px；表格再被 `min-width:36rem` 撑到 576px。
- 决策：删 `.pm-shell`、`.pm-card-grid*`、`.pm-table-wrap` 与 `min-width:36rem`；表格移出卡片网格，作为独立 `.cbi-section` 全宽渲染。
- 验收：768/1280 下表格容器 `clientWidth ≥ 640`，`scrollWidth == clientWidth`；页面横滚 0。
- 若表格列在 768 仍 <60，按 **A** 合并列（PM 的 rill/history 表列数先测再定），或按 **B** 改 `.cbi-value` 明细。

**D3. Aurora `select` 锁死 210px，比字段宽 3px**

- 根因：Aurora `select{max-width:100%;min-width:calc(var(--spacing)*52.5)}`，`--spacing=4px` → 210px；PM settings 320 下字段 207px，`min-width` 胜出，溢出 3px（页面横滚仍为 0）。
- 决策：
  1. **不写插件 CSS**（`min-width:0` 属于 X1/X2 同类的特异性补丁，作废）。
  2. PM settings 的 `form.ListValue` 已经是原生 `select`，`cbi-input-select` 只出现在 benchmark；把 benchmark 的 class 去掉，换取 bootstrap 下同样有样式（不解决 3px）。
  3. 向主题提 issue：`min-width: min(calc(var(--spacing)*52.5), 100%)`。
  4. 若产品不接受 3px：把该字段改为 `form.RadioValue`（原生、无 `min-width`），代价是纵向多 3–5 行；仅在 settings 的该字段使用。
- 验收：`select.right - field.right ≤ 0.5` 视为通过；否则记录为“主题缺陷已上报”，并在验收表标 BLOCKED，不得用插件补丁粉饰。

**D4. 320 下 7/8 页签不可见**

- 根因：主题 `#tabmenu ul.tabs` 是 `overflow-x:auto`，但初始化不滚到 active；`scrollLeft` 全程 0。这是主题行为，不是插件 CSS。
- 决策 **E + 插件兜底**：向主题提 issue（`scrollIntoView({inline:'nearest'})`）；插件侧在页签渲染后对 `ul.tabs > li.active > a` 调一次 `scrollIntoView({inline:'nearest', block:'nearest'})`。
  - 实现位置：各仓页面初始化尾部各 3–5 行（PM `ui.js`、UPNP `overview.js`、CF `utils.js`、NGINX `files.js`），或抽一个约 10 行的公共 helper；挂在 `ui.tabs`/`s.tab()` 生成之后执行。
  - 约束：只用原生 DOM API，不加 CSS、不加断点、不读主题内部结构；不满足这三条的实现不接受。
- 验收：320 宽打开 PM `advanced`，逐一切换页签后 active 的左右边界落在 `ul` 可视区内（±1px）。此项**不再标 BLOCKED**，按插件兜底结果判定。

**D5. 320 下 kv 表 `th`/`td` 各 127px 并排**

- 根因：Aurora 窄屏把 `tr` 变 flex、`td` 占 50%，但 `th` 不参与该契约；KV 表本来就不该用表格表达键值。
- 决策 **B**：`.nm-kv-table`、`.ubr-kv-table`、`.cfi-kv-table` 全部改为 `.cbi-value`（`title` + `field`）。主题在 ≤683 自动堆叠，≥768 并排。
- 验收：320 下不再存在 `th`；768 下键值两列并排；标签非空。

**D6. NGINX 文件表 `min-width:760px` 与堆叠意图互斥**

- 决策：随 D1 一起删；4 列结构下不再需要固定最小宽。

**D7. footer 的窄屏规则**

- 决策：随 X8 删除 footer；若产品坚持保留品牌，只保留纯文本 `<p>`，不加 class、不写 CSS，随主题正文排版。

### 2.4 需要主题侧配合的事项

| 编号 | 请求 | 复现 | 接受标准 |
|---|---|---|---|
| T1 | `.tabs` 初始化/切换后把 active 滚入视野 | 320 宽打开 PM `advanced`，`actL=956`、容器 296、`scrollLeft=0` | 每次切换后 active 的左右边界落在 `ul` 可视区内（±1px）；插件兜底后应恒成立 |
| T2 | `select` 的 `min-width` 不超过容器 | PM settings 320：字段 207、控件 210 | `select.right ≤ field.right + 0.5` |
| T3（可选） | 表格堆叠契约上界从 48rem 提升到 64rem，或提供按容器宽度的表格堆叠 | NGINX files 768：`[76,87,30,52,155,239]` | 768–1024 下 `td` 最小宽 ≥60 且标签非空；D1 落地后本项降级为 nice-to-have |
| T4（仅在上游拒绝 D5 时提交） | `td::before` 在 `th` 场景的等价规则（若上游愿意支持 `th` 堆叠） | kv 表 320：127/127 并排 | `th`、`td` 均为整行宽 |

T1–T4 只作为 issue 提交，不写进任何仓库的验收门槛；T1 的插件兜底按 D4 单独执行，D5 落地后 T4 不再提交。

---

## 3. 例外清单与上限

以下为**允许保留**的自定义 CSS。每条都必须能在第 6 节的静态守卫里按类名白名单放行；未列出的类名一律删。

| 编号 | 类名 | JS 依赖点 | 为什么不能删 | CSS 上限 | 撤销条件 |
|---|---|---|---|---|---|
| E1 | `.nm-log-area` + `.is-empty/.is-loading/.is-error` | NGINX 13（logs 9、certificates 4） | 日志滚动区与状态文案，无原生等价 | 12 行（保留 170–177 排版 8 行；179–183 合并选择器压缩为 3 行、颜色改 `inherit`；1 行注释。删 185–187 与空行） | 原生出现等价日志组件 |
| E2 | `.cfi-log-area` + 状态类 | CF 17 | 同上 | 10 行 | 同上 |
| E3 | `.pm-button--busy` / `button:disabled`（**不得带 `.pm-shell` 前缀**） | PM 2（`ui.js:98,103`） | JS 运行时切换；`.pm-shell` 删除后原选择器会失效 | 2 行 | 改用 `aria-busy` + 原生 `:disabled` |
| E4 | `.ubr-log-area` | UPNP 少量 | 同上 | 10 行 | 同 E1 |
| E5 | `.nm-file-*` 文件浏览器（工具栏、路径行、图标网格、文件表布局） | files.js 多处 | 原生无文件管理器 | 210 行，且无颜色字面量 | 改为原生表格 + 面包屑组件 |
| E6 | `.nm-code-editor` 语法高亮 | site-edit/files | 唯一允许 hex 的地方；**必须收敛为 2 套**（默认 + `[data-darkmode="true"]`）。删 757–817（61 行）、897–946（50 行），补回 7 行 `[data-darkmode="true"]` 选择器，净删 104 行；编辑器区 241→137 行 | 140 行 | 换用带主题 token 的高亮库 |
| E7 | `.pm-stage-list` / `.pm-stage` | PM 4 段进度 | 无原生等价 | 5 行 | 原生出现步骤条 |
| E8 | `.ubr-wizard-*` | wizard.js | 向导步骤条，无原生等价 | 22 行 | 同上 |
| E9 | 统计卡网格 `.pm-*` / `.cfi-*` / `.ubr-*` | 各 view | 数字卡片布局，无原生等价 | PM 0（改原生 section）、CF 30、UPNP 19 | 原生出现统计卡组件 |
| E10 | `.cfi-source-picker` / `[data-cfi-fold]` / `.cfi-sel-summary` | CF 折叠逻辑 | MultiValue 3-chip 截断的 JS 规避，必须配套样式 | 21 行 | 原生 MultiValue 支持折叠 |
| E11 | `.cfi-cmd-box` / `.ubr-cmd-box` | 各 1 | 命令展示，改用 `<pre>` 后只留排版 | 各 7 行 | 无 |
| E12 | `.cfi-collapse-body` / `.cfi-form-map .cfi-collapse-toggle` / `.pm-disclosure` | 折叠容器与开关 | 无原生等价（用 `<details>` 可减到 0） | CF 6 行（3+3）、PM 3 行 | 改用 `<details>` 后删 |
| E13 | `.cfi-form-map` / `.cfi-dashboard` | CF 6（`utils.js:579-581`） | 仅作结构标记；删除容器查询后 **0 行样式** | 0 行 | JS 不再依赖时删 class |
| E14 | `.pm-visually-hidden` | PM 2（`rill.js:28,32`，表格 `<caption>` 文本） | 删掉会让 “Ranking table / Feedback table” 显形 | 1 行 | caption 改用 `aria-label` 或原生 `caption` 隐藏方案后删 |
| E15 | `.nm-code-block` | 证书/配置弹窗 1 处 | 代码块排版；现含 hex/rgba，必须改成 `inherit`/`transparent` | 15 行 | 改用 `.alert-message` 或原生 `<pre>` 样式后删 |
| E16 | `.nm-visit-link` | 概览跳转链接 | 语义色与下划线；颜色改 `inherit`，只留 `text-decoration` | 10 行 | 改用普通 `<a>`/`.cbi-button` 后删 |
| E17 | `.cfi-log-pre` | `diagnostics.js` 日志 `<pre>` | 日志 `<pre>` 的换行与滚动；颜色改 `inherit` | 8 行 | 并入 E2 或改用原生 `<pre>` 后删 |
| E18 | `.ubr-icon` | overview/mappings 内联 SVG | 统一图标尺寸与基线对齐 | 4 行 | 改用主题 icon 或 `.cbi-button` 内图标后删 |
| E19 | `.nm-row-disabled` | files.js 禁用行 | 禁用行降透明度；无原生等价 | 2 行 | 改用 `:disabled` / `.label` 后删 |
| E20 | `.ubr-theme-bootstrap`（body 标记） | `utils.js` 1（`loadSharedCSS` 探测主题样式表后加类）、`mappings.js` 3（三张原生表改用 `.tr/.th/.td` + `data-title`） | **bootstrap 对比度/触摸目标补偿**：主题的 `.label.success`、`.alert-message.success/info/danger` 子元素、`.cbi-button-save/reset/apply` 实测 3.0–4.0:1；按钮 30px、页签 28px 低于 32px 触摸底线。所有规则都以 `body.ubr-theme-bootstrap` 限定，aurora 实测 `body` 无该类、样式零命中。表格窄屏已交回主题堆叠（`tr.tr`/`td.td` + `data-title`），`≤600px` 的 `min-width:640px` 还原段已删除 | 46 行（72–117） | bootstrap 上游修好对比度与触摸目标后删；届时先删本段再跑 §6 守卫 |
| E21 | `.cfi-theme-bootstrap` + `.cfi-table-scroll` + `.cfi-error-details` | `utils.js` 1（探测后加 body 类）、`sources/openclash/diagnostics/intelligence`（四张原生表包裹）、P0 错误面板 `<details>` | **（a）全主题结构规则**（`cloudflare-ip.css` 73–102，30 行，不依赖 body 类，aurora 与 bootstrap 都生效）：`.cfi-table-scroll` 横向滚动、`≤700` 表宽还原、`≤600` 收回 `.tr` 负边距、日志/来源错误折行、折叠 `<summary>` 32px、`≤1048` 模态限宽、`≤420` stats 单列；**（b）bootstrap 补偿**（104–146，43 行，全部以 `body.cfi-theme-bootstrap` 限定）：按钮 32px、save #00713d/白 6.1:1、reset #b3261e、edit #2a6a80、label.success、alert.success/danger 白字 | 43 行（bootstrap 段；a 段 30 行计入瘦身段） | 主题修复对比度/触摸目标/模态宽度后删（b）；表格改主题原生堆叠后删（a）中的滚动与负边距规则 |
| E22 | `.pm-theme-bootstrap` + `.pu-table-scroll` | `ui.js` 1（`ensureStyles` 探测后加 body 类）、`rill.js` 2（两张原生表包裹） | 同 E20 的 bootstrap 补偿（按钮 32px、save #00713d/白、negative #a11414/白、reset #b3261e、dropdown #2a6a80、alert.success/info）；原生表窄屏滚动。全部规则以 `body.pm-theme-bootstrap` 限定 | 38 行（含注释） | 同 E21 |
| E23 | `.nm-theme-bootstrap` + `.nm-table-scroll` + `.nm-cell-wrap` | `utils.js` 1（`loadSharedCSS` 探测后加 body 类）、`sites/backups/certificates/files`（四张原生表包裹）、站点表长单元格折行 | **（a）全主题结构规则**（`nginx-manager.css` 276–308，33 行，aurora 与 bootstrap 都生效）：`.nm-table-scroll` 滚动、`.nm-cell-wrap` 折行、站点表 `td.td/th.th` 允许换行、Actions 列 `td > div.nm-actions` 避免 flex 破坏列、`≤700` 表宽还原 + stats 两列、`≤600` 收回 `.tr` 负边距、Go 按钮 44px、`≤1048` 模态限宽；**（b）bootstrap 补偿**（310–350，41 行，除 348 行外均以 `body.nm-theme-bootstrap` 限定）：按钮/模态输入 32px、save/add/edit/reset/dropdown、label.success、alert.success/danger；348 行 `#view .alert-message details > summary` 是折叠标题触摸目标，与主题无关、全主题生效 | 74 行（结构 33 + bootstrap 41） | 同 E21 |
| E24 | `.ys-tool-footer` 统一版本条 | 四仓共享渲染函数 `renderFooter/appendFooter/renderWithFooter`（UPNP `utils.js`、CF `utils.js`、PM `ui.js`、NGINX `utils.js`）；四仓 32 个视图挂载（含 `_loadError` 空/错分支） | **产品需求**：每页显示“云云舒 · 项目名 · 版本号 + Project/GitHub/X”版本条，四仓结构/样式/文案必须逐字一致，仅 `project`/`repoUrl`/`FOOTER_VERSION` 按仓取值。CSS 段 84 行四仓 sha256 相同；不允许为凑行数预算压缩样式 | 84 行/仓（合计 336） | 产品决定移除版本条，或主题原生提供等价组件 |

**明确不保留**（必须删，不留类名）：

`nm-badge`（10）、`cfi-badge`（23）、`ubr-badge`（15）、`ubr-text-*`（105）、`nm-responsive-table`（4）、`nm-kv-table`/`ubr-kv-table`/`cfi-kv-table`、`nm-inline-setting`、`nm-status-banner`、`cfi-status-banner`、`ubr-status-banner`、`nm-empty-state`、`cfi-empty-state`、`pm-card*`、`pm-field*`、`pm-kv`、`pm-table-wrap`、`*table-wrap`、`ys-tool-footer`、`nm-btn-group`、`ubr-btn-group`、`ubr-mode-bar`。

> 徽标类虽然被 JS 大量引用，但它们是**渲染出口**而非行为钩子：把 `ui.js`/view 里拼 class 的地方改成 `.label success` 即可，CSS 归零。改造前先用 grep 收敛到 0 再删 CSS，避免运行时空 class。

### 3.1 各仓剩余行数目标

| 仓库 | 当前 CSS | 改造后（逐段核算） | 目标上限 | 保留构成 |
|---|---|---|---|---|
| UPNP | 430 | 117 → **202** | ≤145（**+57**，E24） | wizard 22 + stats 19 + log 10 + cmd 7 + icon 4 + 表格滚动容器 4 + 注释/空行 5 + **E20 bootstrap 兼容层 46**（临时，主题修好后删） + **E24 页脚 84** |
| CF | 629 | 146 → **231** | ≤150（**+81**，E24） | 原有瘦身段 103 + **E21 bootstrap 兼容层 43**（临时，主题修好后删） + **E24 页脚 84** |
| PM | 279 | 77 → **162** | ≤80（**+82**，E24） | 原有瘦身段 39 + **E22 bootstrap 兼容层 38**（临时，主题修好后删） + **E24 页脚 84** + 空行 1 |
| NGINX | 1123 | 350 → **435** | **≤450（余 15）** | 文件浏览器 ≤210 + 编辑器 137 + log/stats/表格 ≈25 + **E23 兼容/表格段 74**（临时，主题修好后删） + **E24 页脚 84** |
| **合计** | **2461** | **1030（含 E20–E24 537）** | **≤825（+205）** | 删除 **1431 行（58.1%）**；E20–E24 为临时兼容层 + 统一页脚，去掉后回到 493 |

> 核算口径：按第 2、4 节的实际行段逐行统计（Python 去重），不是各段长度相加。
> - UPNP 由 77 变 81：H2 修正后 `88–91` 归还统计卡网格（+4）。
> - CF 由 110 变 117：`169–174`、`189–195` 按块边界重划（净 0），但保留项含 `.cfi-collapse-toggle`、`.cfi-log-pre` 等此前漏计块；≤110 不可达。落地后实测 146 行（含 E21 43 行），上限改 ≤150。
> - PM 由 40 变 24：删除量按段相加为 255，`.pm-visually-hidden` 移出删除区后又 +1。落地后实测 77 行（含 E22 38 行），上限改 ≤80。
> - NGINX 450 不变：编辑器净删 104 行后为 137；落地后实测 350 行（含 E23 74 行），仍低于 450。
> - UPNP 落地后实测 117 行（含 E20 46 行），低于 ≤145。
> - 2026-11-13 恢复 `ys-tool-footer` 后：四仓各追加同一段 84 行页脚（sha256 一致）。UPNP 202 / CF 231 / PM 162 三仓破限，登记为 E24（页脚为产品需求，不压缩样式凑预算）；NGINX 435 仍在 ≤450 内。
> - 各仓上限相加为 825，仅作单仓门禁；合计以实际 1030 为准，超出部分全部由 E24 页脚（336 行）解释。

目标值是**上限**，不是必须写满。低于上限不补代码。

---

## 4. 分仓实施顺序与验收

顺序：**UPNP → CF → PM → NGINX**。UPNP 结构最接近原生（`form.Map` + `s.tab`），改造完作为另外三仓的模板。

每仓独立分支、独立验收、独立合并；仓与仓之间无代码依赖，可并行，但建议按序做以便复用模板。

每仓的开工基线与舱内顺序（分支依据见第 9 节，中文化范围见第 10 节）：

| 仓 | 开工分支 | 第 1 步 | 第 2 步 | 每步验收 |
|---|---|---|---|---|
| UPNP | `origin/main` 新建 `refactor/native-first` | 中文化：补 2 条 msgid | 瘦身：CSS 349 → ≤85 | ① `msgfmt -c` 0 untranslated、代码串与 po 差集 0；② 4.1 六条 + `wc -l` ≤85 |
| CF | `origin/main` 新建（浅克隆，先 `git fetch --unshallow`） | 中文化：9 个菜单标题已在 po，确认 0 缺口 | 瘦身：CSS 512 → ≤120 | ① 同上 + zh/en 双语言逐页无残留；② 4.1 + `wc -l` ≤120 |
| PM | `origin/main` 新建 | 中文化：`Overview`、`Rill intelligence` 进 po，补 `po/templates` | 瘦身：CSS 255 → ≤40 | ① 同上；② 4.1 + `wc -l` ≤40 |
| NGINX | `origin/main` 新建（先处置 6 个 `M` 文件） | 中文化：`Overview` 进 po，`文件` 改为 `"Files"` 并补 po | 瘦身：CSS 1123 → ≤450 | ① 同上；② 4.1 + `wc -l` ≤450 |

先中文化后瘦身的理由与例外见 10.6；NGINX/CF 未提交改动的处置见 9.2、9.7。

### 4.1 通用验收（每仓都跑）

1. **双主题截图**：bootstrap 25.12.5 与 Aurora 1.2.0，各在 **360 / 768 / 1280** 截改动页，明暗各一套。bootstrap 若仍 500（U2 打包缺陷），该仓标 BLOCKED，**不得**写“bootstrap 通过”。
2. **原生 computed 对照**：取 `admin/status/overview` 与 `admin/system/system` 作为原生基准页，对改造页的 `h2`、`.cbi-section`、`.cbi-button`、`.label` 读取 `color / background-color / border-radius / font-size`，逐项求差，**必须为 0**；不为 0 的项按“仍在自建样式”处理。
3. **窄屏列名**：360 宽下每个 `td` 的 `::before` 内容非空且等于表头；`data-title` 缺失数 = 0。
4. **静态守卫**：跑第 6 节的 9 条 grep，全部达到期望值。
5. **横向滚动**：320/360/390/480/640/768/1024/1280/1920 均为 0。
6. **冒烟**：PM 跑 `scripts/luci_render_smoke.js`；其余仓加载改动页，控制台新增错误 = 0（允许基线已有的 `"%s/%s.js%s".format` 两条）。

### 4.2 UPNP（模板仓）

**删除行段**（`upnp-nat-relay.css`，共 349 行）：

| 行段 | 内容 | 行数 |
|---|---|---|
| 1–7 | `.ubr-dashboard/.ubr-section/.ubr-mt-1/...` 工具类 | 7 |
| 10–15 | `.ubr-text-*` 语义色 + bold | 6 |
| 18–25 | `.ubr-badge` 四色 | 8 |
| 28 | `.ubr-btn-group` | 1 |
| 31–44 | `.ubr-actions` | 14 |
| 55–62 | `.ubr-link` | 8 |
| 70–87 | `.ubr-status-banner` + 动画 | 18 |
| 109–111 | `.ubr-mappings/.ubr-btn-bar` | 3 |
| 136–171 | `.ubr-mode-bar/.ubr-mode-btn` | 36 |
| 172–179 | `.ubr-security textarea` | 8 |
| 190–195 | `.ubr-danger-zone` | 6 |
| 196–219 | `.ubr-table-wrap` | 24 |
| 220–233 | `.ubr-kv-table/.ubr-summary-table` | 14 |
| 235–304 | `.ys-tool-footer` | 70 |
| 305–351 | `@media 600` | 47 |
| 352–430 | `@media 900` 表格堆叠 | 79 |

删除段止于 87，`88–106` 的统计卡网格与卡片（19 行，E9）保留；`46–52`（cmd-box，7 行，E11）、`64–67`（icon，4 行，E18）不在删除段。

**JS 调用点**：`data-label` → `data-title` **16** 处（`mappings.js`）；`ubr-text-*` **105** 处；`ubr-badge` **15** 处；`cbi-input-select` **5** 处；状态横幅 → `.alert-message`；`.ubr-mode-bar` → `form.ListValue` 或 radio。

**验收补充**：`mappings` 页在 360 下四个标签非空；768 下所有列 ≥60；`overview` 的 kv 改 `.cbi-value` 后 320 不再出现 127/127。

**回滚单位**：单仓单分支，按“mappings / overview / 其余页”拆 3 个提交；整仓回滚 = revert 合并提交（squash），单提交回滚按逆序。

### 4.3 CF

**删除行段**（`cloudflare-ip.css`，共 512 行，保留 117 行）：1–10（root 变量 10）、11–14（暗色覆盖 4）、15–19（链接 5）、32–51（badge 20）、52（1）、70–71（2）、72–83（table-wrap 12）、84–99（div 表格 16）、121–128（kv 8）、129–141（actions，含 `!important` 13）、143–155（空态 13）、156–162（复制按钮 7）、169–174（copy-source 6）、176–182（intel 摘要 7）、183–188（6）、189–195（run-history 7）、196–206（empty-value + run-row 11）、239–265（状态横幅 26 + keyframes 1）、277–281（ip 表 5）、284–288（内联注记 5）、291–299（log-controls 9）、301–364（footer 64）、369–376（8）、378–416（39）、418–519（102）、525–629（105）。

**JS 调用点**：`data-label` → `data-title` **11** 处（`sources.js` 8、`openclash.js` 3）；`cfi-badge` **23** 处 → `.label`；`cfi-table-wrap` **6** 处 → 直接 `<table class="table">`；`cfi-form-map` **6** 处保留为标记（0 样式）；`cfi-source-table` 的 `div.tr/div.td` → 真表格；状态横幅 → `.alert-message`；`cbi-input-select` 1 处 → 原生 `select`。统计卡半径改用字面量 `8px`，不再依赖已删除的 `--cfi-radius-card`。

**验收补充**：`sources` 页 360 下 div 表格已不存在；`diagnostics` 日志区仍可滚且颜色跟随主题；`data-cfi-fold` 折叠在 320 下仍生效。

**回滚单位**：单仓单分支，按“CSS 删除 / sources 表格 / 其余页”3 个提交。

### 4.4 PM

**删除行段**（`ui.css`，共 255 行，保留 24 行）：1–16、18–43、45–52、54–70、71–80、81–83、84–101、102–118、120–122、123–125、126–131、132–134、135、138–139、140–141、153–157、160–190、192–275（footer 含其内 `@media 600`）。例外 E3（2 行）、E7（5 行）、E14（1 行，`.pm-visually-hidden` 在 158）与 reduced-motion 块（277–279）不在删除范围；若与上表行段重叠，以例外表为准。

**JS 调用点**：`ui.js` 的 9 个出口 `page/card/badge/kv/note/toolbar/field/inset/tableWrap`（覆盖 8 个 view）；`pm-button--busy` **2** 处保留；`cbi-input-select` **3** 处（benchmark）去 class。

**关键动作**：

- `card()` → `.cbi-section` + `h3` + `.cbi-section-descr`；`badge()` → `.label`；`note()` → `.alert-message`；`kv()` → `.cbi-value`；`toolbar()` → `.cbi-section-actions`；`field()` → `.cbi-value-*`；`tableWrap()` → 返回 `<table class="table">`，不包 div。
- 表格移出 `.pm-card-grid--primary`，作为独立 `.cbi-section` 全宽。
- E3 两条规则改写为无前缀选择器：`.pm-button--busy { cursor:progress; opacity:.78 }`、`.pm-button--busy:disabled`；删壳后加断言 `grep -n '\.pm-shell' ui.css` = 0。

**验收补充**：768 下表格容器 `clientWidth ≥ 640` 且 `scrollWidth == clientWidth`；360 下每行标签非空；`benchmark` 的 select 不再带 `cbi-input-select`。

**回滚单位**：单仓单分支，按“9 个 helper / 逐 view 替换 / CSS 删除”3 个提交。

### 4.5 NGINX（最后做）

**删除行段**（`nginx-manager.css`，下表行段合计 569 行；另编辑器 4 套配色并为 2 套：删 757–817（61 行）、897–946（50 行），补回 7 行 `[data-darkmode="true"]` 选择器，净删 104 行；合计 673 行，保留 450 行）：8–57（badge 50）、60–87（btn-group 28）、88–97（10）、110–119（kv 10）、135–149（log-controls 15）、190–207（暗色 18）、208–224（17）、229–266（38）、267–273（7）、274–279（6）、280–314（35）、315–329（15）、351–421（footer 71）、423–501（79）、503–520（18）、969–1009（权限表 41）、1010–1041（prefers-color-scheme 文件表暗色 32）、1042–1099（58）、1101–1105（5）、1107–1122（16）。

**JS 调用点**：`data-label` → `data-title` **27** 处（files 12、sites 7、certificates 5、backups 3）；`nm-badge` **10** 处 → `.label`；`nm-log-area` **13** 处保留；`nm-responsive-table` **4** 处删除；`cbi-input-select` **12** 处（sites 1、site-edit 3、logs 3、certificates 5）→ 原生 `select`；`body.nm-dark` 引用改 `[data-darkmode]` 或删除。

**文件表 4 列改造**（D1）：`files.js` 合并 Type/Permissions 到 Name 副行，Actions 图标化；同步 12 处 `data-title`。

**验收补充**：768 下 4 列均 ≥60；360 下 4 个标签非空；`logs` 页日志区仍可滚；编辑器在明暗两套下高亮正常（只允许 2 套配色）。

**回滚单位**：单仓单分支，按“footer/响应式 / badge/按钮 / 文件表 4 列 / 编辑器配色”4 个提交。

---

## 5. 与主题的关系

**不锁 Aurora 版本**，也不装版本探针。改为“能力依赖表”：改造后的插件只使用下表能力，换主题时按表评估退化。

| 依赖能力 | Aurora 1.2.0 | bootstrap 25.12.5 | 缺失/退化时的表现 | 严重度 |
|---|---|---|---|---|
| 窄屏表格堆叠（`tr` flex + `td::before`） | 有，断点 48rem | 有移动端样式，但本次容器未验证（U2） | 表格保持横向排布 → 列被压或容器横滑 | 高 |
| `data-title` 契约 | 读（源码检索 + 实测） | 读（源码检索；未在 bootstrap 实测） | 标签为空 → 窄屏无法辨认列 | 高 |
| `.cbi-value` ≤683 堆叠 | 有（1088 次实测） | 有，未逐档实测 | 表单行并排挤压 | 中 |
| `.label` 语义色 | 有 | 有基础 `.label`，语义修饰未逐项实测 | 徽标只剩文字，颜色丢失 | 低 |
| `.alert-message` 语义块 | 有 | 有 | 提示块变普通文本 | 低 |
| `.cbi-button` 及修饰符 | 有 | 有 | 按钮无外观 | 高 |
| `[data-darkmode="true"]` | 有 | 有 | 暗色不跟随 | 中 |
| `--font-sans` / `--font-mono` | 有 | 有 | 排版回退系统字体 | 低 |
| `#tabmenu ul.tabs` | 有，但不自动滚 active | 有 | 窄屏当前页签不可见（D4） | 中 |
| `select` 最小宽 | 210px 锁死（T2） | 未测 | 窄字段溢出 3px | 低 |

**结论**：

- Aurora 换成 bootstrap 时，高风险退化只有两项：表格堆叠（U2 未测）与 `data-title` 标签。二者都必须在 bootstrap 下实测后才能声称兼容；未测前验收表写 BLOCKED。
- 反过来说，插件不再依赖任何主题专有变量后，退化是“布局能力缺失”，不是“颜色错乱/发白”。这是本路线相对旧方案的主要收益。
- 主题升级不需要版本锁；升级后跑一次第 4.1 节的通用验收即可，失败项按 2.3 的五种做法处理。

---

## 6. 静态守卫（可直接进 CI）

以下命令在仓库根目录执行，任一不达期望即失败。

```bash
CSS=<该仓唯一 css 路径>

# 1) 颜色字面量：仅编辑器的标记区间允许
awk '/editor-palette:begin/{skip=1} /editor-palette:end/{skip=0;next} !skip' "$CSS" \
  | grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(|hsla?\('                            # 期望：无输出

# 2) 变量白名单
grep -oE 'var\(--[a-z0-9-]+' "$CSS" | sort -u \
  | grep -vE 'var\(--font-(sans|mono)'                                             # 期望：无输出

# 3) 禁止选择器/属性
grep -n '#maincontent' "$CSS"                                                      # 期望：无输出
grep -rn 'data-label' --include='*.js' --include='*.css' \
  --exclude-dir='test*' --exclude-dir='fixtures' --exclude-dir='node_modules' .     # 期望：无输出
awk '/prefers-reduced-motion: reduce/{skip=1} skip&&/^}/{skip=0;next} !skip' "$CSS" \
  | grep -n '!important'                                                           # 期望：无输出（仅该块内允许）
grep -n '\.pm-shell' "$CSS"                                                        # 期望：无输出（E3 已改无前缀选择器）

# 4) 响应式重排（只放行 prefers-reduced-motion: reduce）
grep -nE '@media|@container' "$CSS" | grep -vE 'prefers-reduced-motion: reduce'     # 期望：无输出

# 5) 自建暗色
grep -rnE 'nm-dark|nm-light|prefers-color-scheme|detectLightMode' --include='*.js' --include='*.css' .  # 期望：无输出

# 6) 单主题 class
grep -rnE 'cbi-input-select|pre\.errors|cbi-button-neutral|cbi-map-title' --include='*.js' --include='*.css' .  # 期望：无输出

# 7) 自造布局/组件 class：CSS 与 JS 双侧逐条对照第 3 节例外表
grep -noE '\.(nm|cfi|pm|ubr)-[a-z0-9-]+' "$CSS" | sort -u                        # 期望：全部在例外表
grep -rhoE "'(nm|cfi|pm|ubr)-[a-z0-9-]+'" --include='*.js' . | tr -d "'" | sort -u  # 期望：全部在例外表

# 8) 内联样式（对象字面量与 el.style.x 两种写法都算）
grep -rnE "style: ?['\"]|\.style\.[a-zA-Z]+ ?=" --include='*.js' .                  # 期望：无输出（例外需登记）

# 9) 手写 div 表格 / 自建徽标与横幅
grep -rnE "table-titles|div\.(tr|td)|'class': ?'(tr|td)'|nm-badge|cfi-badge|ubr-badge|pm-badge|status-banner" --include='*.js' .  # 期望：无输出
```

**行数守卫**（每仓一个上限，超出即失败）：

```bash
test "$(wc -l < "$CSS")" -le 145   # UPNP（实测 117）
test "$(wc -l < "$CSS")" -le 150   # CF（实测 146）
test "$(wc -l < "$CSS")" -le 80    # PM（实测 77）
test "$(wc -l < "$CSS")" -le 450   # NGINX（实测 350）
```

---

## 7. 风险登记

| # | 风险 | 触发 | 影响 | 处理 |
|---|---|---|---|---|
| R1 | 768–1024 主题缺陷未修，4 列仍挤 | D1 后 `Size` <60 | 中 | 退到 B（`.cbi-value` 明细）；或等 T3 |
| R2 | bootstrap 未实测（U2） | 容器 500 | 高 | 验收标 BLOCKED；不得声称兼容 |
| R3 | `data-title` 漏写 | 手写 `td` 未带属性 | 高 | 静态守卫 9 + 360 宽逐格断言 |
| R4 | 删包裹后超宽表格横滑 | 列多且内容长 | 中 | 先做列合并（A），再删 `min-width` |
| R5 | footer 删除遭产品反对 | 品牌展示需求 | 低 | 保留纯文本 `<p>`，0 CSS |
| R6 | 编辑器 hex 例外扩散 | 顺手加色 | 中 | E6 上限 140 行；颜色守卫按 `editor-palette` 标记区间放行 |
| R7 | 徽标/text 类批量替换漏点 | 105 处 `ubr-text-*` | 高 | 先 grep 收敛到 0 再删 CSS；逐页冒烟 |
| R8 | 页签问题长期不修 | 主题排期 | 中 | D4 的插件兜底已覆盖，不阻塞验收；上游修好后删兜底 |
| R9 | select 3px 长期存在 | 主题排期 | 低 | 记录主题缺陷；必要时改 radio |
| R10 | 原生 computed 对照不通过 | 仍残留自建样式 | 中 | 按 4.1 第 2 条逐项定位并删规则 |

---

## 8. 不做的事（明确非目标）

- 不做导航重构（8 个同级页面合并为单页 + tab）：URL 变化，收益与风险不成比例。
- 不写任何面向特定主题的 CSS 补丁（`#maincontent` 前缀、选择器加倍、`[data-aurora]` 之类）。
- 不做暗色适配代码：只读 `[data-darkmode="true"]`，颜色全部继承。
- 不锁主题版本、不加版本探针；用第 5 节能力表 + 通用验收替代。
- 不改四个仓库的构建/打包结构，不新增 CSS 文件。

---

## 9. 分支策略（开工基线）

四仓的默认分支都是 `main`：`git symbolic-ref refs/remotes/origin/HEAD` 均返回 `refs/remotes/origin/main`。下表的 behind/ahead 取自 `git rev-list --left-right --count origin/main...<branch>`；CF 是浅克隆，该命令无 merge base，数值不可用（见 9.7）。

### 9.1 结论表

| 仓 | 远端 HEAD | 本地当前分支 | 工作区 | 应在哪个分支上改 | 依据 |
|---|---|---|---|---|---|
| nginx-manager | `origin/main` `3f3bf4d`（2026-11-11） | `fix/footer-hairline` `8b41525`（behind 12 / ahead 1） | **脏**：6 个 `M`（Makefile、README×2、CSS、utils.js、overview.js） | `origin/main` 新建分支 | 当前分支落后 12；ahead 的 1 个提交改的是 X8 要删的 footer；脏文件含 CSS+JS，不能直接改 |
| cloudflare-ip | `origin/main` `b674b6e`（2026-11-10） | `fix/stable-review-channel` `e56d15a`（相对 upstream 未推送 2） | 仅 `scripts/__pycache__/` 未跟踪 | `origin/main` 新建分支 | 浅克隆，ahead/behind 不可信；未推送的折叠功能与本次瘦身无关 |
| upnp-nat-relay | `origin/main` `d8a3a9e`（2026-11-10） | `main` `d8a3a9e`（= `origin/main`） | 干净，无 stash | `main` 新建分支 | 无未合并工作，唯一 ahead 分支改的也是 footer |
| performance-manager | `origin/main` `b2844af`（2026-11-11） | `main` `b2844af`（= `origin/main`） | 干净，无 stash | `main` 新建分支 | 所有非默认分支均 behind，无超前工作 |

### 9.2 nginx-manager

| 分支 | behind | ahead | 最后提交 | 是否动同一批 CSS+JS |
|---|---|---|---|---|
| `fix/footer-hairline`（当前） | 12 | 1 | 2026-11-09 | 是：`nginx-manager.css` footer `border-top` 1 行 + Makefile 版本 |
| `fix/nginx-dep-virtual-provides` | 2 | 0 | 2026-11-10 | 否（仅 Makefile 依赖） |
| `main`（本地） | 12 | 0 | 2026-08-29 | 否 |
| `origin/main` | 0 | 0 | 2026-11-11 | — |

**结论：从 `origin/main` 新建 `refactor/native-first`。** 依据：唯一 ahead 的 `fix/footer-hairline` 只改 footer 分隔线，而 footer 整块（`351–421`，71 行）在 X8 里要删除，合并它等于给删除制造冲突，直接作废该分支。

**脏工作区处置**：6 个 `M` 逐个定性——Makefile 是版本 `1.8.7→1.8.8`、依赖 `nginx-ssl→nginx`、`@PKG_FULL_VERSION@` 替换；README×2 是文档；CSS 删掉 footer 的 `border-top` 1 行；utils.js 改 CSS 缓存查询参数；overview.js 1 行。与瘦身无关的先单独提交或 `git stash` 到旧分支，再 `git switch -c refactor/native-first origin/main`；**不得带未提交改动切分支**，否则第 6 节行数守卫会把别人的改动算进来。

### 9.3 cloudflare-ip

| 分支 | behind | ahead | 最后提交 | 是否动同一批 CSS+JS |
|---|---|---|---|---|
| `fix/stable-review-channel`（当前） | 不可用（浅克隆） | 相对其 upstream 未推送 2 | 2026-11-10 | 是：`cloudflare-ip.css` +27、`sources.js` +32、`po/en` +4、`po/zh_Hans` +4 |
| `fix/stable-review-channel-clean` | 不可用 | 已随 PR #51 并入 `origin/main` | 2026-11-10 | 是：同批 CSS/JS 的干净版（`origin/main` 已含） |
| `release/2.6.0-r11` | 不可用 | 仅本地，无 `origin` 对应 | 2026-11-09 | 否 |
| `release/2.6.0-r12` | 不可用 | 本地与 `origin` 同为 `3ba341e` | 2026-11-09 | 否 |
| `release/2.6.0-r13` | 不可用 | 本地 `b2ecffa` ≠ `origin` `ed3b1ab` | 2026-11-10 | 否 |
| `main`（本地） | 不可用 | 内容落后 `origin/main` 6 个文件 | 2026-11-09 | 否 |
| `origin/main` | — | — | 2026-11-10 | — |

**结论：从 `origin/main`（`b674b6e`）新建分支，先 `git fetch --unshallow` 再算一次 ahead/behind 存档。** 依据：本地 `main` 缺 PR #51 的 6 个文件改动（CHANGELOG、Makefile、CSS 2 行、`release-channel.json`、测试），不能当基线；`release/*` 是发布快照，不承接新功能。

**未推送的 2 个提交**（`40929d4` 折叠内置来源 + `e56d15a` 截图归档）：不在 `origin/main` 里，也**不并入**本次瘦身分支。若要保留，浅克隆拉全后按 `git rebase --onto origin/main 62c62be fix/stable-review-channel` 单开分支；否则保持原样不动。它与瘦身的冲突面是 `cloudflare-ip.css` 的 `.cfi-source-picker` 段（新增 27 行）和 po 两个文件，而瘦身删的是 `.cfi-table-wrap`/`169–174`/`189–195`/`378–629`，同文件不同段，可分别落地——但不要同分支混做。

### 9.4 upnp-nat-relay

| 分支 | behind | ahead | 最后提交 | 是否动同一批 CSS+JS |
|---|---|---|---|---|
| `main`（当前） | 0 | 0 | 2026-11-10 | — |
| `fix/footer-hairline` | 11 | 1 | 2026-11-09 | 是：`upnp-nat-relay.css` footer `border-top` 1 行 |
| `fix/footer-separator` | 5 | 0 | 2026-11-10 | 否 |
| `origin/fix/upnp-relay-batch2` | 1 | 0 | 2026-11-10 | 否 |
| `origin/fix/upnp-relay-d01-d05-d06` | 3 | 0 | 2026-11-10 | 否 |

**结论：在 `main`（=`origin/main` `d8a3a9e`）新建分支即可。** 依据：工作区干净、无 stash、无未合并本地分支；`fix/footer-hairline` 与 NGINX 同款，改的是 X8 要删的 footer，作废。

### 9.5 performance-manager

| 分支 | behind | ahead | 最后提交 | 是否动同一批 CSS+JS |
|---|---|---|---|---|
| `main`（当前） | 0 | 0 | 2026-11-11 | — |
| `fix/ip-full-dependency` | 9 | 0 | 2026-11-11 | 否 |
| `origin/fix/iproute2-capability-probe` | 6 | 0 | 2026-11-11 | 否 |

**结论：在 `main`（=`origin/main` `b2844af`）新建分支即可。** 依据：工作区干净、无 stash；两个非默认分支都只 behind 不 ahead，且不碰视图 CSS+JS。

### 9.6 有没有“比主线更超前”的长期分支

没有。四仓都不存在 `dev`/`preview`/`next`/`develop` 这类长期并行分支；分支只有 `main`、`fix/*`、`release/*` 三类。逐仓的 ahead 分支共 3 处：

- UPNP `fix/footer-hairline`：ahead 1，behind 11，只改 footer 1 行；
- NGINX `fix/footer-hairline`：ahead 1，behind 12，只改 footer 1 行；
- CF `fix/stable-review-channel`：相对 upstream 未推送 2 个提交，改折叠功能（CSS+JS+po）。

前两个与主线**没有分叉到无法快进**——它们只多 1 个提交、少 11–12 个提交，rebase 成本为零；但那一行属于 X8 要删的 `.ys-tool-footer`，所以结论是**不合并、不 rebase、直接作废**，而不是“分叉太深”。CF 的 2 个提交是唯一需要人决策的：保留就单开分支，不保留就留在原地，两种都不影响 `origin/main` 开工。

### 9.7 CF 浅克隆与多 worktree 的作业约束

- `rev-parse --is-shallow-repository` = `true`，`.git/shallow` 只有 1 行。因此 `rev-list origin/main...<branch>` 返回 475–487 的 ahead，是“没有 merge base”的假数，**不能**据此写成“分支已分叉到无法快进”。
- 判断分支关系改用：`git merge-base --is-ancestor A B`（能答“是不是祖先”）、`git diff --stat A B`（能答“内容差多少”）、`git rev-list --count <branch>@{upstream}..<branch>`（能答“本地未推送几个”）。
- 该仓库是多 worktree：`luci-app-cloudflare-ip`（`main`）、`luci-app-cloudflare-ip-r11`（`fix/stable-review-channel`）、`/private/tmp/cfip-fixwt`、`/private/tmp/cleanup`、`/private/tmp/redact-pr39`、`/private/tmp/redact-pr40`。后 4 个标记 `prunable`，动工前先 `git worktree prune`；只允许在 `luci-app-cloudflare-ip-r11` 目录里操作，避免两个 worktree 同时切分支。
- 另有一个损坏的引用 `refs/remotes/origin/HEAD 2`（重名文件，来源未查），会让 `git for-each-ref` 打一行 warning。它不影响分支判断，动工前一并删掉即可；`origin/HEAD` 本身仍正确指向 `origin/main`。

---

## 10. 全面中文化

### 10.1 底数

“面向用户的字符串”以 `_()` 包裹的 msgid 计；覆盖率为“唯一 msgid 已进 po 且有非空 zh_Hans 译文”的比例。

| 仓 | `_()` 调用 | 唯一 msgid | po 语言 | zh 条目 | 空 msgstr | 代码串不在 po | 覆盖率 | 菜单标题 |
|---|---|---|---|---|---|---|---|---|
| nginx-manager | 759 | 506 | en / zh_Hans / templates | 544 | 0 | **0** | 100% | 8 条：6 条在 po，`Overview` 缺，`文件` 是硬编码中文 |
| cloudflare-ip | 679 | 526 | en / zh_Hans / templates | 563 | 0 | 0 | 100% | 9 条全部在 po 且有中文 |
| upnp-nat-relay | 628 | 457 | en / zh_Hans / templates | 478 | 0 | **2** | 99.6% | 9 条全部在 po 且有中文 |
| performance-manager | 670 | 577 | en / zh_Hans（无 templates） | 577 | 0 | 0 | 100% | 9 条：7 条在 po，`Overview`、`Rill intelligence` 缺 |

分布（`_()` 调用数）：

| 仓 | 视图 JS（`view/*.js`） | 共享 JS（utils/labels/ui） | 菜单 JSON | 模板 `.htm` | CBI lua |
|---|---|---|---|---|---|
| nginx-manager | 758 | 1 | 1 文件 / 8 键 | 0 | 0 |
| cloudflare-ip | 575 | 104 | 1 文件 / 9 键 | 0 | 1（controller，无 UI 串） |
| upnp-nat-relay | 627 | 1 | 1 文件 / 9 键 | 0 | 0 |
| performance-manager | 337 | 333 | 1 文件 / 9 键 | 0 | 0 |

### 10.2 与预期不符的三件事

1. **不是“大量英文没翻”。** 四仓 `_()` 包裹的源串全部是英文，且 po 里 0 条未翻译（`msgfmt --statistics` 实测 544/563/478/577 translated）。真实缺口只有 UPNP 的 2 条 msgid 没进 po：`Click "Detect" to check status.`、`Zone "%s" already exists. Use "Fix Zone Settings" instead.`（`network.js:368,380,387` 等）。NGINX 之前看起来缺的 2 条（`No sites configured…`、`Warning:` 的 HTML 前缀）实测在 po 第 591、1638 行，是转义比对误报。
2. **真正的英文残留是菜单标题。** NGINX 的 `Overview`（`menu.d` 8 键之一）和 PM 的 `Overview`、`Rill intelligence` 不在本包 po 里；NGINX 的 `files` 直接写死中文“文件”，英文界面会看到中文——这是反方向的缺口。
3. **只有两种语言。** 四仓都只发 `en` 与 `zh_Hans`，没有任何其它语言包；如果“全面中文化”的目标只是中文界面，这就够了；如果隐含“多语言”，缺口是 msgid × 目标语言，量级要从这里重算。PM 还缺 `po/templates/*.pot`。

对未包裹英文的判定：按“像人话、含空格、不在 po”扫出 37/17/27/24 条候选，逐条归类后全部是命令（`opkg install`、`apk add`、`uci set`）、路径（`/etc/init.d/acme renew`）、类名与内联样式、HTTP 头（`X-Frame-Options`）、协议名（`TCPing`、`IPv4`）、错误码（`ServiceReadyTimeout`）、品牌（`Cloudflare`、`AWS Route53`），**没有一条是漏翻的 UI 文案**。唯一边界项是 NGINX 证书页的占位符 `KEY=VALUE\nKEY2=VALUE2`，属格式示例，建议保留。

### 10.3 做法：统一走 LuCI 的 po/i18n，不内嵌中文

- 四仓都已 `include $(TOPDIR)/feeds/luci/luci.mk`，`po/<lang>/<pkg>.po` 自动编译进包，零构建改动；新语言只需加目录。
- 菜单 JSON 的 `title` 由 LuCI 按本包 catalog 翻译，po 有则译、无则原样显示——10.2 的缺口正好一一对应。
- 内嵌中文（把源码字面量直接写中文）会把英文界面也变成中文，且与现有 500+ msgid 体系重复，四仓统一排除。
- 唯一保留的内联中文是品牌“云云舒”/`@云云舒`（NGINX `utils.js:125,136`、CF `utils.js:561,572`、UPNP `utils.js:181,192`、PM `ui.js:168,179`），它不是 UI 文案。

### 10.4 不翻译清单（守卫的 allowlist）

| 类别 | 实例 | 处理 |
|---|---|---|
| 品牌 | 云云舒、`@云云舒`、GitHub、Cloudflare、Alibaba Cloud、Huawei Cloud、AWS Route53、GoDaddy、Namecheap、DNSPod / Tencent | 原样 |
| 命令与路径 | `opkg install`、`apk add`、`uci set …`、`/etc/init.d/acme renew`、`nginx.conf` | 原样 |
| 环境变量/字段 | `CF_Token`、`CF_Account_ID`、`CF_Zone_ID`、`DP_Id`、`DP_Key`、`Ali_Key`、`Ali_Secret`、`HUAWEICLOUD_Username` | 原样 |
| HTTP 头/协议 | `X-Frame-Options`、`Content-Security-Policy`、`Strict-Transport-Security`、`TCPing`、`HTTPing`、`IPv4`/`IPv6`、`TLSv1.2 TLSv1.3` | 原样 |
| 内部枚举/错误码 | `ServiceReadyTimeout`、`SaveApplyCancelled`、`RunStatusTimeout`、`Status file not found`、`Runtime · Disabled`（作字典 key，值已 `_()`） | 原样 |
| 日志/API 原文匹配 | `No data`、`ubus code 5`、`未收到数据`（用于判断，不展示） | 原样 |
| 格式串 | `%s`、`{n}`、`KEY=VALUE` | 原样 |

### 10.5 验收判据

1. **po 完整**：`msgfmt -c --statistics po/zh_Hans/<pkg>.po` → `0 untranslated`（四仓现状已满足，改造后不得回退）。
2. **代码串 ⊆ po**：抽 `_()` 的唯一 msgid 与 po `msgid` 求差集，必须为 0（当前 UPNP 差 2，其余 0）。
3. **菜单标题**：`menu.d/*.json` 每个非空 `title` 要么是本包 po 的 msgid，要么在 10.4 清单内；`Overview`、`Rill intelligence` 必须进 po，NGINX `files` 的 `title` 从硬编码“文件”改为 `"Files"` 并在 `po/zh_Hans` 补 `文件`（JSON 里不能写 `_()`，只能靠 po）。
4. **运行时双语**：`zh_CN` 下逐页截图无英文句子；`en` 下逐页无中文（品牌除外）。这一条同时覆盖“本包 po 缺失时是否被 luci-base 兜底”的不确定性，不靠推断。
5. **allowlist 对账**：未包裹英文的扫描命中数 = 10.4 清单命中数，多一条即失败。

### 10.6 与样式改造的先后：先中文化，后瘦身

每仓先落 1 个纯 i18n 提交（JS 字面量 / po / 菜单 JSON），再进 CSS 与结构批次。理由：

- 中文化不碰 CSS 类名、DOM 结构与行数，做完即可单独验收、单独回滚；
- 先冻结 msgid，瘦身阶段的目标只剩“原生判据 + 行数”，不会把“翻译没补齐”和“样式没删净”混在同一次验收里；
- 反过来先瘦身，`_()` 串集合会变（NGINX 文件表合并列要改表头、PM 的 9 个 helper 会改标签），中文化得重扫一遍。

例外：瘦身批次内新增或改写的文案（D1 合并列的副行标签、图标按钮的 `aria-label`）在该批提交里同步补 po，不单独开批次。

### 10.7 会不会把 672 行推高：不会

- 中文化不改任何 `.css`，新增代码只落在 `.js`、`.po`、`menu.d/*.json`，第 6 节的行数守卫与 3.1 的 672 行不受影响。
- 菜单标题与按钮文案变短（中文 2–6 字 vs 英文 6–18 字符），只会减少换行，不需要新规则。
- 不引入语言相关选择器（`html[lang]`、`:lang()` 之类），否则会同时违反 1.2 白名单。
- 唯一交叉点是文件级：NGINX 脏工作区与 CF 未推送提交里都有 po/CSS 改动，所以 9.2/9.3 要求先处置再切新分支；这是作业顺序问题，不是行数问题。

---

## 附录 A：本次核对到的关键实测值

| 事实 | 数值 | 用途 |
|---|---|---|
| 页面级横向滚动 | 0 / 1088 次 | 改造后不得回归 |
| NGINX 768 文件表列宽 | `[76,87,30,52,155,239]` | D1 依据；`Size` 30px |
| NGINX 1025 正常列宽 | `[224,91,67,68,180,277]` | 现状基准 |
| UPNP/NGINX kv 表 320 | `tr=flex`、`th`/`td` 各 127px | D5 依据 |
| PM wrap 768 | `278/576` | D2 依据 |
| PM wrap 1920 | `497/576`（恒 79px） | D2 依据；推翻“1280 起不横滑” |
| PM select 320 | 控件 210、字段 207、溢出 3 | D3 依据 |
| 页签 active 不可见 | 320 下 7/8 页；`scrollLeft=0` | D4 依据 |
| `data-label` JS 计数 | CF 11 / UPNP 16 / NGINX 27 / PM 0 | 改造工作量 |
| `ubr-text-*` 引用 | 105 处 | UPNP 最大替换项 |
| `nm-log-area` | 13 处 | E1 |
| `cfi-badge` | 23 处 | 改 `.label` |
| `nm-badge` | 10 处 | 改 `.label` |
| 变量交集 | `{--font-sans, --font-mono}` | 1.2 白名单 |
| 四仓 CSS 总量 | 2461 行 | 核算后 672 行（-72.7%），目标 ≤680 |

## 附录 B：旧文档处置

| 文档 | 处置 |
|---|---|
| `luci-responsive-refactor-plan-2026-11-11.md` | 开头加“已被取代”标记；内容保留作历史。其中 X1–X8 对应的手法不得实施 |
| `luci-responsive-breakpoint-audit-2026-11-11.md` | 开头加“已被取代”标记；第 1–6 节测量数据继续有效，第 7 节优先级作废 |
| `luci-native-style-audit-2026-11-10.md` | 保留为契约依据；第 5 节的行段估算以本方案第 4 节为准（已核对实际行号） |

---

*本文件为只读审计后的规划产物，未修改四个仓库的任何文件。*
