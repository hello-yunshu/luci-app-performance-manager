# 四仓 LuCI 插件响应式断点审计报告

> **本文档的优先级与实施映射已被 `luci-native-first-plan-2026-11-12.md` 取代。**
> 第 1–6 节的测量数据继续有效；第 7 节“建议优先级”及 P0–P7 批次映射作废——新路线不再使用插件侧特异性补丁与自定义断点。

- 审计日期：2026-11-11
- 审计对象：`luci-app-upnp-nat-relay`、`luci-app-cloudflare-ip-r11`、`luci-app-performance-manager`、`luci-app-nginx-manager`
- 运行环境：OpenWrt 25.12.5（r33051）/ LuCI 25.12.5 / Aurora 1.2.0 / Chrome for Testing 1243（Playwright，linux/amd64 容器，端口 8089）
- 测量规模：**1088 次页面测量**（17 个宽度 × 32 个页面 × 明暗两套），**197 张截图**
- 原始数据：`/tmp/luci-audit/merged.jsonl`（1088 行）、`/tmp/luci-audit/results3-*.jsonl`、截图 `/tmp/luci-audit/shots3/`
- 性质：**只读审计**。未修改四仓任何文件，未提交，未切分支，未改动设备配置。

---

## 0. 先读这一节：两处旧结论作废

> 这两条在此前的口头/阶段汇报里出现过，已被实测推翻。后续任何人改代码前先看这里，不要拿旧说法当依据。

### 更正 1：不存在“两种导航模型”，`cbi-tabmenu` 不是第二种导航

旧说法把内页 `ul.cbi-tabmenu` 当成与主题 `#tabmenu ul.tabs` 并列的第二种导航模型，**该说法作废**。

实测事实：

| 项目 | 结果 |
|---|---|
| 页面级导航 | 只有 `#tabmenu ul.tabs` 一种，四仓 32 个页面全部如此 |
| `ul.cbi-tabmenu` 出现范围 | 仅 `upnp/network` 一个页面，共 **2 组**，每组 2 项（`Status / Configuration`、`Zone Status / Zone Configuration`） |
| 它的性质 | `section` 内部的**原生选项卡控件**（`li.cbi-tab` / `li.cbi-tab-disabled`），不是页面级导航 |
| 响应式表现 | 320–1920 全程 `scrollWidth == clientWidth`、`clip = 0`、`activeOut = false`，**不产生任何响应式问题** |

结论：**需要做响应式处理的导航只有 `.tabs` 一种**。不要按“两套导航要做两套适配”去改代码，也不要在 `cbi-tabmenu` 上加班加点。

附注（自我更正）：阶段一口头汇报里写的“`cbi-tabmenu` 出现 0 次”也不准确。合并数据中有 32 条记录命中了它（仅 `upnp/network`，明暗各 16 档），只是行为正常所以未单列。以本节为准。

### 更正 2：卡片换行后高度不齐，不成立

旧说法认为卡片换行后同一行高度不一致。实测：

| 项目 | 结果 |
|---|---|
| 网格样本 | 193 组 |
| 同行高度差（按 `Math.round(top/4)` 分组，仅比较同一行） | **最大 0px** |
| 跨行高度差 | 存在，但这是正常的内容差异，不是缺陷 |

结论：**不要**为它加 `align-items: stretch`、统一 `min-height` 或 JS 等高脚本。旧结论里的“高度不齐”是把不同行混在一起比较造成的误判。

---

## 1. 方法与可复现性

### 1.1 测量方式

- 真实浏览器（Chrome for Testing 1243）+ Playwright，逐页 `setViewportSize → goto → waitForSelector('#maincontent') → 400ms → evaluate`。
- 明暗两套：Aurora 默认 `data-darkmode="false"`；暗色通过 `document.documentElement.setAttribute('data-darkmode','true')` 注入后重测。
- 宽度档位（17 档）：`312, 320, 360, 390, 414, 480, 640, 683, 768, 820, 853, 960, 1024, 1152, 1280, 1440, 1920`。其中 312/683/853/960/1152 对应 125%/150% 缩放后的有效宽度。
- 每档采集：`documentElement.scrollWidth / clientWidth`、视口外元素、表格可见列宽与容器宽、网格同行高度差、`.cbi-value` 堆叠数、按钮尺寸、`.tabs` 的 `sw/cw/overflowX/scrollLeft`、active tab 是否在容器视野内、文本裁剪（`scrollWidth > clientWidth`）、错误态/只读态、`select` 控件宽与最长选项文本宽。

### 1.2 数据可信度说明

- 表格列宽只统计 `width > 0` 的可见列，避免隐藏列把 `min` 拉成 0。
- 卡片高度只在**同一行**内比较，跨行不比较。
- 行级行为（`tr`/`td` 的 `display`、`::before` 的 `content` 与实测宽度）用独立探针在同一容器复测，避免只读 CSS 推断。
- 容器内页面为**无后端数据的空态**（CF/UPNP 多数页面、PM 表体），因此“有数据行时的换行/截断”属于未验证项，见第 2 节。

---

## 2. 未验证项（明确标注，不得当作缺陷结论）

以下 5 项在本次环境中**无法验证或未验证**。报告与方案中凡是涉及它们的地方，都保留「未验证」标签；任何改造动作都必须先补测再改。

| # | 未验证项 | 为什么未验证 | 当前能说的 | 不能说的 |
|---|---|---|---|---|
| U1 | **PM 表格在窄屏的实际行内行为** | 审计时 PM 表体无数据行，只测到表头与容器 | 容器 `.pm-table-wrap` 内 `scrollWidth 576 / clientWidth 288`，页面级横滚 = 0，横滑发生在容器内（已实测） | 不能说“PM 表格窄屏可用”或“PM 表格窄屏不可用”；行内长文本换行、操作列挤压均未观察 |
| U2 | **bootstrap 主题** | 容器内 bootstrap 模板不全，加载返回 500；官方 apk 仍失败，判定为打包缺陷 | 仅验证 Aurora 明/暗两套 | 不能把 Aurora 的结论外推到 bootstrap；bootstrap 下 `data-title`/`.tabs` 行为未知 |
| U3 | **长目录名 / 长路径** | 容器内最长文件名仅 `.dockerenv`（10 字符），最长目录层级浅 | `.dockerenv` 在 768px 下 117×94、换行正常；ellipsis 裁剪 0 例 | 不能说“长路径不会撑破布局”；80+ 字符目录名、深层路径未测 |
| U4 | **CF / UPNP 有数据行时的表格堆叠** | 两仓页面为空态，`tbody` 无数据行 | 合成 DOM 探针验证了 CSS 契约：CF `td::before content="Source"`、`tr=block`；UPNP `content=""`、`tr=flex` | UPNP 的“结构同 NGINX、大概率同样坏”是**推断**，不是观测；CF 的堆叠在有数据时是否溢出未测 |
| U5 | **原生下拉（MultiValue/dropdown）展开态** | 展开面板由 JS 动态插入，且部分页面无选项数据；未做展开后的逐档测量 | 折叠前的 chips 行为、CF 的折叠阈值逻辑已读码并实测折叠生效 | 不能断言展开面板在 320px 下不溢出；面板定位、最大高度、滚动均未测 |

> 说明：U4 里 UPNP 与 NGINX 的 CSS 选择器完全同构（`.xxx td::before{content:attr(data-label)}` + `tr{display:block}`），NGINX 在有数据行的 files 页已实测坏掉；因此 UPNP 的风险等级高，但**结论仍标注为推断**。

---

## 3. 四仓横向对比

### 3.1 总览

| 维度 | performance-manager | cloudflare-ip | upnp-nat-relay | nginx-manager |
|---|---|---|---|---|
| 页面数 | 8 | 8 | 8 | 8 |
| 页面级横向滚动（1088 次） | 0 | 0 | 0 | 0 |
| 导航模型 | `.tabs` | `.tabs` | `.tabs`（另有 1 页 section 内 `cbi-tabmenu`） | `.tabs` |
| `.tabs` 内容宽 | 1195–1248px | 850–1248px | 966–1248px | 790–1248px |
| 首次完整可见所需宽度 | **1280** | **960** | **1152** | **960** |
| 表格实现 | 原生 `<table class="table">` | `div.table > div.tr > div.td` | 原生 `<table>` | 原生 `<table>` |
| 窄屏表格策略 | 容器内横滑（`min-width:36rem`） | 自定义堆叠（`max-width:900` + `@container`） | 自定义堆叠（`max-width:900`） | 自定义堆叠（`max-width:1024`） |
| 窄屏表格实际结果 | 横滑；**全宽度存在**（1920 仍 79px） | 堆叠契约成立（合成 DOM；真实表未渲染，U4） | 堆叠被主题覆盖（推断，U4；已用合成行复现） | 767 以下被主题接管、768–1024 退化 |
| 标签属性 | 不用（原生表） | `data-label`（JS 11 处 + CSS 4 处） | `data-label`（JS 16 处 + CSS 1 处） | `data-label`（JS 27 处 + CSS 1 处） |
| MultiValue 折叠 | 无 MultiValue | **有**（JS + `data-cfi-fold`） | 无（当前 2 项可容纳） | 无 MultiValue |
| 自定义暗色 | 否（用主题变量） | 否 | 否 | **是**（166 个硬编码色值 + `prefers-color-scheme`） |
| 插件断点 | 560/600/720/760/768/900 | 600/900（媒体查询）+ 600/900（容器查询） | 600/900 | 600/720/1024 |

### 3.2 同组件跨仓表现不一致（单列）

| 组件 | PM | CF | UPNP | NGINX | 判定 |
|---|---|---|---|---|---|
| 响应式表格 | 不堆叠，全宽度横滑 | 正确堆叠 | 堆叠失效（推断，U4） | 半失效（768–1024 退化） | **四个仓四种命**，必须统一 |
| 单元格标签 | 无 | `data-label`，生效 | `data-label`，被主题的 `data-title` 顶掉 | 同 UPNP | 属性契约不统一 |
| 表格断点 | 无（靠容器宽） | 900 | 900 | 1024 | 与主题 768 全都不对齐 |
| MultiValue | — | 折叠 | 不折叠 | — | 同组件两种策略 |
| 暗色来源 | 主题变量 | 主题变量 | 主题变量 | 自建色板 + `prefers-color-scheme` | NGINX 是唯一双开关 |
| 表单标签堆叠 | ≤683 堆叠 | ≤683 堆叠 | ≤683 堆叠 | ≤683 堆叠 | **一致，无缺陷** |

### 3.3 一致且正常的部分（避免过度改造）

- `.cbi-value` 堆叠：四仓统一在 683/768 之间切换，均为 ≤683 全堆叠、≥768 全并排，无异常。
- 按钮尺寸：`tiny = 0`（1088 次），最小高度 ≥ 32px，320px 下无点击目标过小问题。
- 文本裁剪：`ellipsis / 截断` 实测 0 例。
- 卡片网格：同行高度差恒 0（见更正 2）。
- 页面级横向滚动：0/1088。
- 暗色容器层：未发现硬编码浅色底（`lightInDark` 全 0）。

---

## 4. 断点 × 页面 × 缺陷矩阵

图例：

- `T` = `.tabs` 溢出（可横滑，但当前页签可能看不见）；这是**仓库级**现象，同仓 8 页一致
- `X` = 表格退化：多列被压扁（实测最窄列 < 60px）
- `Y` = 表格堆叠但单元格标签为空、值被挤到极窄
- `H` = 表格在容器内横向滚动（设计选择，页面本身不横滚）
- `C*` = 表格堆叠契约正确，但无数据行（未验证，见 U4）
- `·` = 该档未观察到上述缺陷

| 仓库 | 页面 | 320 | 390 | 480 | 640 | 768 | 820 | 1024 | 1280 | 1440 | 1920 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| pm | overview | T | T | T | T | T | T | T | · | · | · |
| pm | benchmark | T | T | T | T | T | T | T | · | · | · |
| pm | optimize | T | T | T | T | T | T | T | · | · | · |
| pm | capabilities | T | T | T | T | T | T | T | · | · | · |
| pm | rill | T·H | T·H | T·H | T·H | T·H | T·H | T·H | · | · | · |
| pm | history | T | T | T | T | T | T | T | · | · | · |
| pm | settings | T | T | T | T | T | T | T | · | · | · |
| pm | advanced | T | T | T | T | T | T | T | · | · | · |
| cf | overview | T | T | T | T | T | T | · | · | · | · |
| cf | settings | T | T | T | T | T | T | · | · | · | · |
| cf | advanced | T | T | T | T | T | T | · | · | · | · |
| cf | sources | T·C* | T·C* | T·C* | T·C* | T·C* | T·C* | · | · | · | · |
| cf | intelligence | T | T | T | T | T | T | · | · | · | · |
| cf | diagnostics | T·C* | T·C* | T·C* | T·C* | T·C* | T·C* | · | · | · | · |
| cf | openclash | T·C* | T·C* | T·C* | T·C* | T·C* | T·C* | · | · | · | · |
| cf | passwall | T·C* | T·C* | T·C* | T·C* | T·C* | T·C* | · | · | · | · |
| upnp | overview | T | T | T | T | T | T | T | · | · | · |
| upnp | network | T | T | T | T | T | T | T | · | · | · |
| upnp | wizard | T | T | T | T | T | T | T | · | · | · |
| upnp | settings | T | T | T | T | T | T | T | · | · | · |
| upnp | security | T | T | T | T | T | T | T | · | · | · |
| upnp | mappings | T·C* | T·C* | T·C* | T·C* | T·C* | T·C* | T | · | · | · |
| upnp | openclash | T | T | T | T | T | T | T | · | · | · |
| upnp | diagnostics | T | T | T | T | T | T | T | · | · | · |
| nginx | edit | T | T | T | T | T | T | · | · | · | · |
| nginx | certificates | T | T | T | T | T | T | · | · | · | · |
| nginx | sites | T | T | T | T | T | T | · | · | · | · |
| nginx | overview | T | T | T | T | T | T | · | · | · | · |
| nginx | core-config | T | T | T | T | T | T | · | · | · | · |
| nginx | files | T·Y | T·Y | T·Y | T·Y | T·X | T·X | T·X | · | · | · |
| nginx | backups | T | T | T | T | T | T | · | · | · | · |
| nginx | logs | T | T | T | T | T | T | · | · | · | · |

> 640/768 之间的 `T` 分布以实测 `clip > 0` 为准；960/1152 等缩放档位见附录 A。

### 4.1 `.tabs` 溢出的精确数据

| 仓库 | 320 clip | 390 | 480 | 640 | 768 | 820 | 960 | 1024 | 1152 | 1280 |
|---|---|---|---|---|---|---|---|---|---|---|
| pm | 899 | 829 | 739 | 579 | 491 | 441 | 307 | 246 | 123 | **0** |
| cf | 554 | 484 | 394 | 234 | 146 | 96 | **0** | 0 | 0 | 0 |
| upnp | 670 | 600 | 510 | 350 | 262 | 212 | 78 | 17 | **0** | 0 |
| nginx | 494 | 424 | 334 | 174 | 86 | 36 | **0** | 0 | 0 | 0 |

### 4.2 当前页签可见性（真实浏览器实测）

`#tabmenu ul.tabs` 是 `overflow-x: auto`，但**浏览器不会自动把 active 页签滚进视野**，`scrollLeft` 全程为 0。

| 宽度 | 抽查 8 页中“当前页签完全不可见” | 典型值 |
|---|---|---|
| 320 | **7 / 8** | PM advanced `actL=956`，容器宽 296 |
| 390 | **7 / 8** | PM advanced `actL=956`，容器宽 366 |
| 480 | **6 / 8** | PM advanced `actL=956`，容器宽 456；NGINX files 转为可见 |
| 768 | **5 / 8** | UPNP diagnostics `actL=874`，容器宽 704；CF intelligence、NGINX files 转为可见 |
| 1280 | 0 / 8 | 全部可见 |

后果：窄屏用户打开页面时，看不到自己当前在哪一页，只能盲滑标签条。这是本次审计里**影响面最大、最直接**的问题。

---

## 5. 缺陷按根因归类

### A. 原生组件行为（主题/框架层，插件无法单独修好）

| 编号 | 现象 | 证据 | 归属 |
|---|---|---|---|
| A1 | `.tabs` 溢出后不自动滚到 active 页签，`scrollLeft=0` | 4.2 表，320 下 6/8 不可见 | **主题层**；插件只能加兜底 JS |
| A2 | `select` 最小宽 210px，窄容器里溢出字段 | PM settings 320：字段 207px、控件 210px，溢出 3px；最长选项文本 280px，≤390 被截断 | **主题层**（`min-width` 写死） |
| A3 | 原生表格移动端契约是 `td::before{content:attr(data-title)}`，不是 `data-label` | Aurora 规则：`td::before{--tw-content:attr(data-title);display:none}`，窄屏改为 `display:block` | **框架层**；插件用错属性就落空 |
| A4 | MultiValue 原生最多显示 3 个 chip 且硬截断长标签 | CF 代码注释与实测一致；`>3` 或任一 chip `scrollWidth>clientWidth` 即折叠 | **框架层**；CF 已用 JS 规避 |
| A5 | `.cbi-value` 在 683/768 之间整体切换堆叠 | 四仓一致 | 框架层，**正常，无需处理** |

### B. 自定义 CSS 覆盖失败（插件层，可直接修）

| 编号 | 现象 | 机理（特异性） | 涉及 |
|---|---|---|---|
| B1 | NGINX 768–1024 表格退化成 6 列挤扁，`Size` 列仅 30px | 插件 `td{display:flex}` 为 `(0,1,1)`，Aurora `:is(table.table,.table) td` 为 **`(0,1,2)`**，无条件生效 → `display:table-cell` 反杀 | nginx-manager.css 448–457 |
| B2 | ≤767 单元格标签为空但仍占位，值被挤到约 8px | 插件写 `content:attr(data-label)`；Aurora 在窄屏强制 `td::before{content:attr(data-title);display:block;margin-bottom}`，插件没有 `data-title` → 空字符串标签占满一行 | nginx-manager.css 459–468、upnp-nat-relay.css 383–392 |
| B3 | ≤767 行变成 `display:flex`、单元格两列一行 | Aurora 窄屏 `tr{display:flex;flex-wrap:wrap}` `(0,1,2)` 覆盖插件 `tr{display:block}` `(0,1,1)` | nginx 434–446、upnp 361–372 |
| B4 | 768–1024「死区」：主题不接管、插件又被打败 | 插件断点 900/1024 与主题 768 不对齐，中间区间两套规则都不完整 | nginx 423、upnp 352 |
| B5 | NGINX 暗色有 166 个硬编码色值 + `prefers-color-scheme`，与主题 `data-darkmode` 是两套开关 | 系统暗色但主题亮色（或反之）时配色错位；当前环境未触发，属“未爆的雷” | nginx-manager.css 190/757/897/1010/1107 |

### C. 布局模式选错（插件层，需要产品决策）

| 编号 | 现象 | 说明 |
|---|---|---|
| C1 | PM 表格不堆叠，靠 `min-width:36rem` 容器横滑 | 页面不横滚（已实测），但 320 下必须横向滑动才能看全列；这是**选择**不是 bug |
| C2 | CF 用 div 版表格 + 极高特异性（`.cfi-source-table > .tr:not(.table-titles) > .td` = `(0,3,0)`），是唯一在窄屏契约成立的仓 | 代价：媒体查询与 `@container` 两套重复实现（418–484 与 555–610） |
| C3 | NGINX 文件表同时有 `min-width:760px` 与堆叠媒体查询 | 两套意图互斥，导致 768–1024 既没堆叠也没横滑，直接挤扁 |
| C4 | 四仓各写一套响应式表格，无共享契约 | 同组件四种结果（见 3.2），长期必然继续分叉 |
| C5 | CF 的 `@container` 与 `@media` 是**两套等价实现**（不是死代码） | `utils.js:579-581` 的 `appendFooter` 已对任何 `.cbi-map`（排除 `.cfi-dashboard`）补 `cfi-form-map`，`cloudflare-ip.css:525-527` 因此在正常路径也设置 `container-type:inline-size`；`@container (max-width:900px)`（555–610）会命中。真正的问题是 418–484 的 `@media` 版本与它重复，改布局时要同步两处 |

### 5.1 主题层 vs 插件层：谁该修什么

| 问题 | 主题层能修 | 插件层只能规避 |
|---|---|---|
| A1 active 页签不可见 | ✅ 主题在 `#tabmenu` 初始化时 `scrollIntoView({inline:'nearest'})` | 插件可加一次性兜底（不推荐，四份重复） |
| A2 `select` min-width 210px | ✅ 改成 `min-width: min(calc(var(--spacing)*52.5), 100%)` | 插件侧：`#maincontent .cbi-value-field select{min-width:0}`（`max-width:100%` 压不住，`min-width` 胜） |
| A3 `data-title` 契约 | ✅ 已存在，无需改 | ✅ 插件改用 `data-title`，或提高特异性继续用 `data-label` |
| B1–B4 覆盖失败 | ❌ 主题不应为插件让路 | ✅ **只能插件自己修**（提特异性或改用原生契约） |
| B5 暗色双开关 | ❌ 主题无法感知插件自建色板 | ✅ **只能插件自己修**（删自建色板，改用主题变量） |
| C1–C4 布局模式 | ❌ | ✅ 插件层决策 |

一句话：**A1/A2 去推主题；B/C 全部自己消化。**

---

## 6. 逐仓结论

### 6.1 nginx-manager（问题最集中）

- 8 页 `.tabs` 内容宽最小 790px（部分页签展开后到 1248px），<960 全部溢出；`logs` 在 320/390/480/768 下 active 页签均不可见，`files` 在 320/390 不可见、480/768 才可见。
- `files` 页表格三档三种形态（实测同一台机器、同一页面）：
  - `≤767`：`tr=flex`、`wrap=wrap`、`td=block`、`flex-basis:50%`、6 个 `td` 各 126px（320 时）、`td::before` 内容为空且宽 118px（320）/308px（700），行高 212px，值区被压到极窄；
  - `768–1024`：`tr=block` 但 `td=table-cell`，6 列宽 768 时 `[76, 87, 30, 52, 155, 239]`（行高 116），800–1024 时 `[76, 89, 30, 53, 158, 243]`（行高 81），`Size` 列恒为 30px；
  - `≥1025`：`tr=table-row`，列宽 `[224, 91, 67, 68, 180, 277]`（1025）/`[285, 115, 84, 86, 229, 352]`（1280），正常。
- `overview` 的 `.nm-kv-table` 在 320 下 `tr=flex`、`th`/`td` 各 127px 并排（实测），768 起才恢复 `block`；同一根因（Aurora 窄屏 `tr{display:flex}` 胜 `.nm-kv-table tr` `(0,1,1)`），此前报告漏记。
- 暗色：166 个硬编码色值 + `@media (prefers-color-scheme: dark)`，与主题 `data-darkmode` 不同步。
- 文案：`sites/edit` 菜单 `title` 为 `None`；“文件”一项未翻译（`menu.d` 中缺 i18n）。

### 6.2 upnp-nat-relay

- 8 页 `.tabs` 内容宽最小 966px，完整可见需 1152px；1024 下仍差 17px。
- `mappings` 页表格与 NGINX 完全同构（`data-label` + `tr{display:block}` + 900 断点），按特异性推导必然同样失效；但页面无数据行，**结论标注为推断（U4）**。
- `network` 页有 2 组 section 内 `cbi-tabmenu`，宽度自适应、不溢出，无需处理。
- `overview` 的 `.ubr-kv-table` 在 320 下同样 `tr=flex`、`th`/`td` 各 127px 并排（实测），768 起恢复 `block`；与 NGINX kv 表同根因。
- `security.js:37` 用 `form.MultiValue('protocols')`，未做折叠；当前只有 TCP/UDP 两项，可容纳。

### 6.3 cloudflare-ip

- 唯一在窄屏 CSS 契约成立的仓（div 表格 + `(0,3,0)` 特异性）；但真实页面依赖 `source-registry` RPC，本次环境只渲染出错误态，表格未真实出现，故仍归入 U4。
- **容器查询不是死代码（更正）**：`utils.js:579-581` 的 `appendFooter` 已给所有 `.cbi-map`（排除 `.cfi-dashboard`）补 `cfi-form-map`，因此 `cloudflare-ip.css:525-527` 的 `container-type:inline-size` 在正常渲染路径也生效，`@container (max-width:900px)`（555–610）会命中。此前只看 `sources.js` 错误分支，漏了 `appendFooter`，结论作废。
- 问题在维护成本：`@media (max-width:900px)`（418–484）与 `@container (max-width:900px)`（555–610）是两套等价实现；`@container` 依赖祖先 `container-type`，改布局时容易只改一套。
- `MultiValue` 折叠是四仓唯一实现：监听 `cbi-dropdown-change/close`，检测 `li[display]` 是否 `scrollWidth>clientWidth`，命中则 `data-cfi-fold`，摘要显示 `Selected: %d`。
- `.tabs` 内容宽 850px，≥960 完整可见。

### 6.4 performance-manager

- 8 页 `.tabs` 内容最宽（1195–1248px），完整可见需 **1280px**，是四仓里最晚收敛的。
- 表格走另一条路：`.pm-table-wrap{overflow-x:auto}` + `.table{min-width:36rem}`，页面不横滚，容器内横滑。实测容器 `scrollWidth/clientWidth`（rill 页，fresh load）：320 `576/231`、360 `576/271`、390 `576/301`、480 `576/386`、640 `576/537`、768 `576/278`、820 `576/295`、900 `576/331`、1024 `576/387`、1025 `576/387`、1152 `576/444`、1280 `576/497`、1440 `576/497`、1920 `576/497`。
- **更正：横滑不是只在窄屏发生**。`.pm-table-wrap` 位于 `.pm-card-grid--primary` 的两列网格里（primary card 544px、内容列 499px），1280/1440/1920 下 wrap 仍是 497px，而表格 `min-width` 576px，**始终有 79px 横滑**；768–1024 因为主题切双列表单，内容列反而缩到 278–387px，横滑距离比手机还大（320 是 231px 宽、345px 可滑）。此前写“1280 起不再横滑”是错的。
- 表体无数据行，行内行为**未验证（U1）**。
- `settings` 320 下 `select` 控件 210px vs 字段 207px，溢出 3px；最长选项 280px（U2 之外的另一项主题层限制 A2）。
- 审计期间曾因容器缺 `/etc/config/performance-manager` 触发 RPCError，错误横幅长串把 `scrollWidth` 撑到 403；补配置后归零。结论：**错误态的长字符串才会撑破页面**，正常态不会。

---

## 7. 建议优先级（不含实施方案，方案见独立文件）

| 优先级 | 事项 | 对应方案批次 | 理由 |
|---|---|---|---|
| P0 | 补测 U1–U5 | P0 | 未验证项不能作为改造依据 |
| P1 | 修 NGINX 768–1024 死区、≤767 空标签、kv 表并排、空态 colspan | P1 | 唯一有数据行、可完整实证的破版 |
| P2 | 修 UPNP 标签属性与特异性（含 kv 表） | P2 | 同一套改法，两仓可并行 |
| P3 | 主题侧提 issue：active 页签滚入视野 | P5 | 影响全部插件，插件侧重复修不划算 |
| P4 | PM 表格：≥1024 卡片全宽、窄容器堆叠或横滑 | P4 | 实测 1920 仍有 79px 横滑 |
| P5 | `select` 210px 超出字段 3px | P7 | 主题 `min-width:calc(var(--spacing)*52.5)` |
| P6 | CF 媒体查询/容器查询去重（可选） | P3（可选） | 两套等价实现，不改行为 |
| P7 | 收敛原生 `data-title`、清理 NGINX 暗色板 | P6 | 长期方向，动作最大，最后做 |

---

## 附录 A：17 档完整测量索引

| 档位 | 来源 | 覆盖 |
|---|---|---|
| 312 | 125% 缩放等效 | 全 32 页 × 明暗 |
| 320 / 360 / 390 / 414 / 480 | 手机主流 | 全 32 页 × 明暗 |
| 640 | 主题断点 | 全 32 页 × 明暗 |
| 683 / 853 / 960 / 1152 | 125%/150% 缩放等效 | 全 32 页 × 明暗 |
| 768 / 820 / 1024 / 1280 / 1440 / 1920 | 平板/桌面 | 全 32 页 × 明暗 |

## 附录 B：关键截图

| 文件 | 内容 |
|---|---|
| `/tmp/luci-audit/shots3/light-320-nginx-files.png` | NGINX 文件页 320：空标签 + 两列挤压 |
| `/tmp/luci-audit/shots3/zoom-320-nginx-row.png` | 单行放大：标签空、值被压 |
| `/tmp/luci-audit/shots3/zoom-768-nginx-row.png` | 768：6 列挤扁，`Size` 30px |
| `/tmp/luci-audit/shots3/light-320-pm-settings.png` | PM 设置页 320：`select` 溢出字段 |
| `/tmp/luci-audit/shots3/light-320-pm-rill.png` | PM 表格容器横滑 |
| `/tmp/luci-audit/shots3/dark-390-nginx-files.png` | 暗色下 NGINX 文件页 |

## 附录 C：复现命令

```bash
cd /tmp/luci-audit/runner
# 全量（明/暗）
MODE=light node audit3.js light
MODE=dark  node audit3.js dark
# 单仓
REPO=nginx node audit3.js light
# 行级探针（NGINX files）
node nf.js
# active 页签可见性
node tabs.js
```
