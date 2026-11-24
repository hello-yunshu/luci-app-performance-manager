# 四个 LuCI 插件「去主题化 / 回归原生样式」深度审计

- 审计日期：2026-11-10
- 基线：OpenWrt **25.12.5**（`r33051-f5dae5ece4`，x86/64，见 `.portable-rootfs/etc/openwrt_release`）
- 参照主题：**bootstrap 25.12.5**（原生默认）与 **Aurora 1.2.0**
- 范围：仅分析，**未修改任何仓库文件、未提交、未切换分支、未改设备配置**

---

## 0. 结论速览

**一句话**：四个仓库没有一个是「基本原生」的。它们全部自带一套视觉外壳，区别只在于外壳的深浅。四个仓的 CSS 里，被两个主题**同时定义**的 CSS 变量只有 2 个（`--font-sans`、`--font-mono`）——也就是说今天写的每一行 `var(--xxx, #hex)` 都至少在一个主题下走硬编码 fallback。

**严重度排序（从最该改到最不急）**

| 排名 | 仓库 | 自定义 CSS 行数 | 硬编码颜色（出现/去重） | 判断 |
|---|---|---|---|---|
| 1 | nginx-manager | 1123 | 166 / 39 | **最严重**。四套调色板 + 自建暗色检测 + 文件浏览器 + 代码编辑器 |
| 2 | cloudflare-ip-r11 | 629 | 35 / 12 | **严重**。22 个变量里 10 个在 25.12 根本不存在；手写 div 表格；两段重复响应式约 200 行 |
| 3 | upnp-nat-relay | 430 | 54 / 9 | **中等**。结构最接近原生（`form.Map` + `s.tab`），但 98 处 `.ubr-text-*` 全压死变量 |
| 4 | performance-manager | 279 | 22 / 19 | **最轻**，但仍有 26 行 Aurora 预览残留与 2 个不存在的变量 |

**必须纠正的五个初始假设**

1. ❌「四个插件用了废弃的 `cbi-tabmenu`」→ **不成立**。`cbi-tabmenu` / `cbi-tab` 是 25.12 的**现役**内页标签组件（`ui.js` `initTabGroup`），四个仓的 JS 里**一次都没直接用过**。
2. ❌「`ui.addNotification` 是旧接口」→ **不成立**。它是 25.12 现役 API，四仓大量使用是正确的（共 100+ 处）。
3. ❌「bootstrap 不样式化 `.btn`」→ **不成立**（本次实测纠错）。`cascade.css` 里有 `.item::after,.btn,.cbi-button{...}`，`.btn` 在 bootstrap 下有完整按钮外观。但 `.btn` 不是 CBI 契约，仍建议改 `.cbi-button`。
4. ❌「bootstrap 没有语义色变量」→ **部分不成立**。bootstrap 定义了 `--success-color-high/low/medium`、`--warn-color-*`、`--error-color-*`；但**没有**插件里写的 `--success-color` / `--warning-color` / `--danger-color`（无后缀），所以插件引用的仍然是死变量。
5. ✅「原生菜单栏是滑块」→ **在 Aurora 下成立，但结论要改写**：滑块是 `.cbi-tabmenu`（内页标签），而四个插件顶部那条是 `#tabmenu > ul.tabs`（主题子菜单，下划线样式）。这是**导航模型**差异，不是组件版本落后。

---

## 1. 基准与证据等级

| 结论 | 等级 | 依据 |
|---|---|---|
| 25.12.5 原生 `cbi-map` / `cbi-section` / `cbi-value` / `table` / `label` / `alert-message` 的 DOM 与 class | **实测** | 本机 `.portable-rootfs`（25.12.5）+ LuCI 25.12 源码 `form.js` / `ui.js` |
| bootstrap 25.12.5 定义的全部 77 个 CSS 变量 | **实测** | 解析 `.portable-rootfs/www/luci-static/bootstrap/cascade.css` |
| Aurora 1.2.0 定义的全部 166 个 CSS 变量 | **实测** | 解析 `main.css`（190 KB） |
| 两主题变量交集 = 2 个 | **实测** | 集合运算：`{--font-sans, --font-mono}` |
| `.cbi-tabmenu` 在 Aurora 是药丸滑块、`.tabs` 是下划线 | **实测** | Aurora `main.css` 规则原文（见 §2） |
| 插件顶部栏走 `.tabs` | **实测** | 四仓 `menu.d` 均为同级子项；`menu-aurora.js` / `menu-bootstrap.js` 渲染 `#tabmenu > ul.tabs` |
| 四仓 CSS/JS 的行号、变量、颜色计数 | **实测** | 脚本统计 + 定点 grep（见各表） |
| 登录后页面的 computed style | **未取得** | 设备 `/cgi-bin/luci/` 返回 403，未登录；结论由 CSS 级联推断 |
| 「暗色下走浅色 fallback 会发白」 | **推断** | 依据：变量未定义 + `var(x, #fff)` 语义。需改造后在真机复核 |
| 改造后剩余行数 | **推断** | 按块估算，误差约 ±10% |

**设备只读探测结果**：`192.168.2.1` 可达，Aurora **1.2.0**；CF 的 CSS 已部署但比仓库旧一版（602 行 vs 629 行）；UPNP / NGINX 与仓库**字节一致**；PM **未安装**（`ui.css` 404）。Aurora 的 patches 目录中**没有**这四个插件的专用补丁。

---

## 2. 「菜单栏不一样」的真相

### 2.1 原生有两层标签，长得不一样

| 层 | 组件 | DOM | bootstrap 25.12.5 | Aurora 1.2.0 |
|---|---|---|---|---|
| **主题子菜单**（页面顶部切换同级页面） | 由主题渲染 | `#tabmenu > ul.tabs > li.tabmenu-item-* > a` | 与 `.cbi-tabmenu` **共用同一条规则**，圆角上标签 | **下划线**：`.tabs>li.active{border-bottom:2px solid var(--text)}` |
| **内页标签**（一个页面内切换） | `ui.tabs.initTabGroup()` / `s.tab()` | `ul.cbi-tabmenu > li.cbi-tab` | 同上，圆角上标签 | **药丸滑块**：`.cbi-tabmenu{background:var(--surface-sunken);border-radius:calc(var(--radius-base)*4);border:1px solid var(--hairline);padding:var(--spacing);display:flex}`，激活项 `.cbi-tabmenu li.cbi-tab a{background:var(--text);color:var(--surface)}` |

实测规则原文（bootstrap）：

```css
.tabs,.cbi-tabmenu { --tab-bar-background-color:var(--background-color-high); ... }
.tabs > li,.cbi-tabmenu > li { border-radius:4px 4px 0 0; border-bottom:none; ... }
```

也就是说：**在原生默认主题下两者视觉一致；只有 Aurora 才把 `.cbi-tabmenu` 做成滑块。** 用户看到的「滑块」是 Aurora 的 `.cbi-tabmenu`。

### 2.2 四个插件为什么是「老样子」

四仓的 `menu.d` 全部注册为**同级页面**：

```
admin/network/performance-manager/{overview,optimize,benchmark,capabilities,rill,history,settings,advanced}
admin/services/cf_ip/{overview,settings,advanced,sources,intelligence,logs,openclash,passwall}
admin/services/upnp_nat_relay/{overview,wizard,settings,network,security,mappings,openclash,diagnostics}
admin/services/nginx-manager/{overview,sites,certificates,files,core-config,backups,logs}
```

同级页面 → LuCI 走 `#tabmenu` → 主题渲染 `ul.tabs` → Aurora 给下划线。**这不是插件写错，是导航模型选择的结果。**

原生 Firewall 也一样：`admin/network/firewall/{zones,forwards,rules,snats,ipsets,custom}` 是同级页面，顶部同样是 `.tabs` 下划线。所以「原生是滑块」只对**内页标签**成立（如 `status/routes`、`system/startup`、`dashboard/index`）。

### 2.3 唯一例外：UPNP 的 Network 页

`upnp-nat-relay/.../view/upnp-nat-relay/network.js:243-244, 553-554` 使用了 `s.tab('status', ...)` / `s.tab('config', ...)`，渲染为 `.cbi-tabmenu` —— **四仓中唯一会显示 Aurora 药丸滑块的页面**。

### 2.4 想统一成滑块，只有两条路

| 方案 | 代价 | 是否推荐 |
|---|---|---|
| 把 8 个同级页面合并成 1 个页面 + `ui.tabs()` | URL / 书签全变，路由重构，非纯样式改动 | 仅在确实需要「单页多 tab」时做 |
| 由主题把 `#tabmenu .tabs` 改成滑块 | 影响所有插件与原生 Firewall | 主题侧决策，不是插件的事 |

**插件的正确做法**：不要为了模仿滑块写 CSS。保持同级菜单 + `.tabs`，把样式完全交给主题。

---

## 3. 组件版本核对（「用了旧组件」逐项）

| 组件 / API | 25.12.5 状态 | 证据 | 四仓使用情况 | 结论 |
|---|---|---|---|---|
| `cbi-tabmenu` / `cbi-tab` | **现役** | `ui.js` `initTabGroup`；bootstrap 与 Aurora 均有完整规则 | JS 中 0 处直接使用；UPNP 通过 `s.tab()` 间接生成 | **不需要替换** |
| `ui.tabs.initTabGroup` | **现役** | `system/startup.js:129`、`status/routes.js:274`、`dashboard/index.js:158` | 0 处 | 可选升级点 |
| `ui.addNotification` | **现役** | `ui.js` 内部实现，核心页面在用 | PM 10 处、CF 多、UPNP 多、NGINX 多 | **不是旧接口，保留** |
| `cbi-map-title` | **不存在** | bootstrap 0 定义 / Aurora 0 定义 / core JS 0 引用 | CF 2 处、NGINX 2 处 | **自造 class，应删** |
| `data-title` | **原生契约** | `ui.js` `ui.Table` 写入；bootstrap 与 Aurora 都读 | **四仓合计 0 处** | 应改用它 |
| `data-label` | **非原生** | 两主题 CSS 均无 `data-label`；只有插件自己的 CSS 读 | CF 11、UPNP 16、NGINX 27 | **旧式写法，应换 `data-title`** |
| 手写 div 表格 `.table > .tr > .td` | 过时写法 | 原生用 `<table class="table">` 或 `ui.Table` | CF `sources.js:126-135` 等 | 换成真表格 |
| `body.nm-dark` / `nm-light` + `detectLightMode()` | **自造** | 原生标准是 `[data-darkmode="true"]`（两主题都支持） | NGINX `utils.js:12,55-57,734`；CSS `208-224, 789, 904, 911, 941` | **应删，改用原生属性** |
| `.btn`（单独使用，无 `cbi-button`） | 仍被 bootstrap 样式化，但不是 CBI 契约 | `cascade.css` 有 `.btn` 规则 | CF 5 处、NGINX 32 处 | 建议补 `.cbi-button` |
| `cbi-button-neutral` | 仅 bootstrap 有 | Aurora 无该 class | NGINX 3 处 | 改 `cbi-button` / `cbi-button-reset` |
| `pre.errors` | 仅 Aurora 有 | bootstrap 无 | 少量 | 改用 `.alert-message.danger` |
| `cbi-input-select` | 仅 Aurora 有 | bootstrap 无 | 少量 | 用原生 `select` |
| 旧 Lua `Table` / `Grid` API | 不适用 | 四仓全 JS | 0 处 | — |

**结论**：四仓**没有**用「已废弃的 LuCI 组件」，但普遍用了**原生契约之外的替代品**（`data-label`、自造 class、手写表格），并把它们误当作原生。

---

## 4. 变量契约（本报告最关键的一节）

### 4.1 三档交叉表（实测）

四仓共引用 **73 个不同的 CSS 变量**。按主题定义情况分档：

| 变量 | bootstrap 25.12.5 | Aurora 1.2.0 | 档位 |
|---|---|---|---|
| `--font-sans` / `--font-mono` | ✅ | ✅ | **原生（唯一跨主题可用）** |
| `--background-color-high/medium/low` | ✅ | ❌ | 主题专有（bootstrap） |
| `--border-color` / `--border-color-medium` | ✅ | ❌ | 主题专有（bootstrap） |
| `--text-color-high/low/medium/highest` | ✅ | ❌ | 主题专有（bootstrap） |
| `--primary-color-high/medium/low` | ✅ | ❌ | 主题专有（bootstrap） |
| `--bg` `--surface` `--surface-sunken` `--text` `--text-muted` `--brand` `--hairline` `--danger` `--success` `--warning` `--radius-base` `--spacing` | ❌ | ✅ | 主题专有（Aurora） |
| `--main-color` `--success-color` `--warning-color` `--danger-color` `--subtext-color` `--text-color` `--background-color` `--background-color-a` `--background-color-highest` `--base-color` `--cbi-background` `--primary-color` | ❌ | ❌ | **根本不存在** |

> 注意：`--success-color-high` 存在（bootstrap），但插件写的是 `--success-color`（无后缀），所以**仍然是死变量**。

### 4.2 逐仓死变量清单

| 仓库 | 引用但**两主题都没有**的变量 |
|---|---|
| PM | `--primary-color`、`--background-color-highest`（应为 `--primary-color-high`、`--background-color-high`） |
| CF | `--main-color`、`--success-color`、`--warning-color`、`--danger-color`、`--subtext-color`、`--text-color`、`--background-color-a`、`--background-color`、`--base-color` + 10 个 `--cfi-*` 自造 token |
| UPNP | `--main-color`、`--success-color`、`--warning-color`、`--danger-color`、`--subtext-color`、`--background-color`、`--background-color-a` |
| NGINX | `--main-color`、`--danger-color`、`--subtext-color`、`--cbi-background` + 18 个 `--nm-code-*` 自造 token |

### 4.3 白名单结论（直接回答「插件到底只允许用哪些变量」）

> **不绑定主题的插件，允许直接依赖的 CSS 变量只有两个：`--font-sans`、`--font-mono`。**
> **颜色、背景、边框、圆角、阴影、间距：一个都不许用 `var()`。**

理由：两主题的变量交集就是这两个；其余任何变量名都至少会在一个主题下失效。所谓「用主题注入变量实现 C 类自定义」在 LuCI 25.12 的现实中不成立——**因为不存在跨主题的语义 token**。

C 类自定义组件的正确取色方式，按优先级：

1. **不取色**（`currentColor`、`inherit`）—— 最安全；
2. 用**原生语义 class** 的既有颜色：`.label.success` / `.alert-message.danger` / `.cbi-button-negative`；
3. 实在需要独立容器（日志框、代码块），只设 `border:1px solid; border-radius` 和排版，**颜色全部继承**。

---

## 5. 每仓分类表

分类口径：**A** 可删｜**B** 可换原生｜**C** 必要自定义｜**D** 主题耦合。

### 5.1 performance-manager（ui.css 279 行 / 121 选择器 / 35 个变量 / 22 处 hex）

| 位置（行） | 当前写法 | 类 | 建议 | 删行 |
|---|---|---|---|---|
| 1-16 | `:root` 定义 13 个 `--pm-*`，其中 `--brand/--surface/--text/--hairline/--success/--warning/--danger/--radius-base/--shadow-lg` 是 Aurora 专有，`--primary-color`/`--background-color-highest` 不存在 | **D** | 整块删除；改用原生 class | 16 |
| 18-43 | `body[data-aurora-preview="true"]` 覆盖 token + 控件外观 | **A** | JS 引用 0 处，Aurora 预览残留 | 26 |
| 45-52 | `.pm-shell` 自建 1180px 居中容器 | **A** | `#maincontent` 已限宽，重复 | 8 |
| 54-57 | `.pm-page-header` + `.pm-page-heading` | **B** | 换 `.cbi-map` + `h2[name="content"]` + `.cbi-map-descr` | 4 |
| 58-64 | `.pm-page-title` / `.pm-page-description` / `.pm-page-mark`（三根装饰竖条） | **B/A** | 标题用原生 h2；`.pm-page-mark` 纯装饰删 | 7 |
| 66-70 | `.pm-page-content` grid | **A** | 原生 `.cbi-map` 已有间距 | 5 |
| 71-80 | `.pm-preview-nav` / `.pm-preview-screen`（含 `[aria-current]`） | **A** | 预览残留，JS 0 引用 | 10 |
| 81-83 | `.pm-status-row` / `.pm-status-label` | **B** | 用 `.cbi-section` + `.label` | 3 |
| 84-101 | `.pm-card-grid` / `.pm-card` / `.pm-card-title`（含 `::before` 竖条） | **B** | 换 `.cbi-section` + `h3` + `.cbi-section-descr`；`::before` 删 | 18 |
| 102-118 | `.pm-badge` + success/warning/danger | **B** | 换 `.label` + `.success/.warning/.danger` | 17 |
| 120-122 | `.pm-kv` dl/dt/dd | **B** | 换 `.table` 两列或 `.cbi-value` | 3 |
| 123-125 | `.pm-note` + `--success/--warning` | **B** | 换 `.alert-message.info/.success/.warning` | 3 |
| 126-131 | `.pm-toolbar` | **B** | 换 `.cbi-section-actions` / `.cbi-page-actions` | 6 |
| 132-134 | `.pm-field` / `.pm-field-label` / `.pm-control-help` | **B** | 换 `.cbi-value` / `.cbi-value-title` / `.cbi-value-description` | 3 |
| 135 | 全局 `:focus-visible` 描边 | **A** | 主题已有 focus 样式 | 1 |
| 136-137 | `.pm-button--busy` / `button:disabled` | **C** | JS `ui.js:98,103` 依赖，保留但去 hex | 2 |
| 138-139 | `.pm-card .cbi-button` / `.pm-toolbar .cbi-button` 尺寸覆盖 | **A** | 原生按钮尺寸足够 | 2 |
| 140-141 | `.pm-inset` / `.pm-inset-title` | **B** | 换嵌套 `.cbi-section` | 2 |
| 142-146 | `.pm-stage-list` / `.pm-stage` / `--active` / `.pm-stage-status` | **C** | 四段进度无原生等价，保留；去 hex | 5 |
| 147-152 | `.pm-disclosure` + `pre` | **B** | 用 `<details>` + 原生 `pre`（保留 `max-height`） | 6 |
| 153-157 | `.pm-table-wrap`（`min-width:36rem`、`overflow-x`） | **A/B** | 原生 `.table` 自带横向滚动；删包裹 | 5 |
| 158 | `.pm-visually-hidden` | **A** | 用 `hidden` 属性或 `aria-label` | 1 |
| 160-189 | 3 段 `@media` 重排 | **A** | 原生已响应式 | 30 |
| 194-276 | `.ys-tool-footer`（硬编码 `#2f7df6` + `rgba()`） | **A/D** | 四仓复制的品牌页脚，建议整体删；保留则必须去色 | 83 |

**PM 小计**：A 9 项 / B 10 项 / C 2 项 / D 2 项；279 行 → **约 25-40 行**（若保留 footer 则 +80）。

> 补充：`ui.js` 的 `page()`(27)、`card()`(42)、`badge()`(19)、`kv()`(48)、`note()`(71)、`toolbar()`(67)、`field()`(75)、`inset()`(83)、`tableWrap()`(90) 是 8 个 view 共用的出口。改这 9 个函数即可覆盖全仓，是本仓最大的杠杆点。

### 5.2 cloudflare-ip-r11（cloudflare-ip.css 629 行 / 167 选择器 / 22 个变量 / 35 处 hex）

| 位置（行） | 当前写法 | 类 | 建议 | 删行 |
|---|---|---|---|---|
| 1-10 | `:root` 10 个 `--cfi-*`（多数是 19.07 变量别名） | **D** | 全删 | 10 |
| 11-14 | `:root[data-darkmode="true"]` 覆盖 | **A** | 属性本身原生，但覆盖应在主题侧 | 4 |
| 15-19 | `.cfi-dashboard a` / `.cfi-form-map a` 全局链接色 | **A** | 主题职责 | 5 |
| 20-27 | `.cfi-dashboard` / `.cfi-form-map` 容器 | **C** | `utils.js:581` 会加 `cfi-form-map`，保留 1 条 | 8 |
| 28-31 | `.cfi-dashboard .cbi-section.cfi-stat-card` | **C** | 统计卡，保留 | 4 |
| 32-51 | `.cfi-badge` + green/red/orange/gray + dark override | **B** | 换 `.label` + 语义修饰 | 20 |
| 52 | `.cfi-btn-group` | **A** | 原生无对应，也不需要 | 1 |
| 53-59 | `.cfi-cmd-box` | **C** | 换 `<pre>` 并只留排版 | 7 |
| 60-69 | `.cfi-log-area` + `.is-empty/.is-loading/.is-error` | **C** | JS 17 处依赖；`--subtext-color`/`--danger-color` 改 `currentColor` | 10 |
| 70-71 | `.cfi-value-full` 强制 `.cbi-value-title` 宽度 | **B** | 原生 `.cbi-value` 布局 | 2 |
| 72-83 | `.cfi-table-wrap` + 子选择器 | **A** | 原生 `.table` 已含滚动 | 12 |
| 84-99 | `.cfi-source-table` 手写 div 表格（`.tr/.th/.td`） | **B** | 换 `<table class="table">` | 16 |
| 100-120 | `.cfi-source-picker` / `.cfi-sel-summary` / `[data-cfi-fold]` | **C** | 折叠选择器，保留 | 21 |
| 121-128 | `.cfi-kv-table` | **B** | 换 `.table` 或 `.cbi-value` | 8 |
| 143-155 | `.cfi-empty-state` | **B** | 换 `.alert-message.info` | 13 |
| 156-162 | `.cfi-copy-btn` | **B** | 换 `.cbi-button` | 7 |
| 163-168 | `.cfi-collapse-body` | **C** | 折叠容器，保留 | 6 |
| 169-171 | `.cfi-copy-source` | **A** | 无样式意义 | 3 |
| 183-188 | `.cfi-technical-details` | **B** | 换 `<details>` | 6 |
| 189-198 | `.cfi-run-history td` | **B** | 换 `.table` | 10 |
| 207-238 | `.cfi-stats-grid` / `.cfi-stat-card` | **C** | 统计卡保留（去 hex） | 32 |
| 239-264 | `.cfi-status-banner`（含 `#maincontent` 选择器 + 渐变 + hex） | **D/B** | 换 `.alert-message`；`#maincontent` 选择器必须删 | 26 |
| 301-364 | `.ys-tool-footer` | **A/D** | 整删 | 64 |
| 372-377 | `#tabmenu .tabs` / `.cbi-tabmenu` focus 覆盖 | **A** | 主题职责 | 6 |
| 418-524 | `@media max-900` 整段（含 443/476 `attr(data-label)`） | **A** | 与原生响应式重复 | 107 |
| 529-628 | `@container` 响应式（527 `container-type`，570/599 `data-label`） | **A/B** | 删，改 `data-title` | 100 |

**CF 小计**：A 8 项 / B 8 项 / C 5 项 / D 3 项；629 行 → **约 90-120 行**。

> CF 是四仓里「**看起来原生、实际全靠兜底色**」最典型的一个：`--main-color`、`--subtext-color`、`--success-color` 全部不存在，Aurora 暗色下所有徽标/日志/状态色都退回浅色 hex。

### 5.3 upnp-nat-relay（upnp-nat-relay.css 430 行 / 115 选择器 / 13 个变量 / 54 处 hex）

| 位置（行） | 当前写法 | 类 | 建议 | 删行 |
|---|---|---|---|---|
| 1-7 | `.ubr-dashboard` / `.ubr-section` / `.ubr-mt-1` / `.ubr-mb-1` / `.ubr-ml-05` / `.ubr-flex-center` 工具类 | **A** | 用原生 `.cbi-section` + 行内不需要的删 | 7 |
| 10-14 | `.ubr-text-success/danger/warning/muted/primary` | **B** | JS **98 处**依赖；先替换成 `.label`/`.alert-message` 再删 | 5 |
| 15 | `.ubr-text-bold` | **A** | 原生 `strong` | 1 |
| 18-25 | `.ubr-badge` + green/red/orange/gray | **B** | 换 `.label`（15 处 JS 引用需同步） | 8 |
| 28 | `.ubr-btn-group` | **A** | 删 | 1 |
| 31-44 | `.ubr-actions` + `!important` 按钮间距 | **A** | 原生 `.cbi-section-table` 已处理 | 14 |
| 46-52 | `.ubr-cmd-box` | **C** | 换 `<pre>` | 7 |
| 55-62 | `.ubr-link` | **A** | 主题职责 | 8 |
| 64-69 | `.ubr-icon` | **C** | SVG 尺寸，保留 | 6 |
| 70-91 | `.ubr-status-banner` + running/stopped/starting + 脉冲动画 | **B** | 换 `.alert-message` + `.label`；动画可删 | 22 |
| 88-108 | `.ubr-stats-grid` / `.ubr-stat-card` / `.ubr-stat-value` | **C** | 统计卡保留（去 hex） | 21 |
| 109-111 | `.ubr-mappings` / `.ubr-btn-bar` | **A** | 删 | 3 |
| 114-135 | `.ubr-wizard-progress/dot/line/step-card/nav` | **C** | 步骤条无原生等价，保留 | 22 |
| 136-171 | `.ubr-mode-bar` / `.ubr-mode-btn`（自造分段选择器） | **B** | 换 `cbi-tabmenu`/radio group | 36 |
| 172-179 | `.ubr-security textarea` | **B** | 原生 textarea | 8 |
| 180-189 | `.ubr-log-area` + 状态类 | **C** | JS 依赖，保留 | 10 |
| 190-195 | `.ubr-danger-zone` | **B** | 换 `.alert-message.danger` + `cbi-button-negative` | 6 |
| 196-219 | `.ubr-table-wrap` + 子选择器 | **A** | 原生 `.table` 已滚动 | 24 |
| 220-234 | `.ubr-kv-table` / `.ubr-summary-table` | **B** | 换 `.table` | 15 |
| 235-352 | `.ys-tool-footer` | **A/D** | 整删 | 118 |
| 305-351 | `@media max-600` | **A** | 原生已响应式 | 47 |
| 352-430 | 响应式表格 + `attr(data-label)` | **A/B** | 删，改 `data-title` | 79 |

**UPNP 小计**：A 8 项 / B 7 项 / C 4 项 / D 1 项；430 行 → **约 60-90 行**。

> UPNP 是四仓里**结构上最接近原生**的（`form.Map` + `s.tab`），问题集中在「用 19.07 变量模拟语义色」，而不是结构性自造。

### 5.4 nginx-manager（nginx-manager.css 1123 行 / 202 选择器 / 30 个变量 / 166 处 hex / 39 个去重色）

| 位置（行） | 当前写法 | 类 | 建议 | 删行 |
|---|---|---|---|---|
| 8-57 | `.nm-badge` + success/warning/error/disabled | **B** | 换 `.label`（10 处 JS 引用需同步） | 50 |
| 60-87 | `.nm-btn-group` | **A** | 删 | 28 |
| 88-98 | 响应式表格第一段 | **A** | 删 | 11 |
| 110-119 | `.nm-kv-table` | **B** | 换 `.table` | 10 |
| 135-149 | `.nm-log-controls` | **B** | 换 `.cbi-section-actions` | 15 |
| 154-207 | `.nm-code-block` | **C** | 代码块保留（去 hex） | 54 |
| 170-189 | `.nm-log-area` + 状态类 | **C** | JS 13 处依赖，保留 | 20 |
| 190-207 | `@media (prefers-color-scheme: dark)` 调色板 | **D/A** | 与原生 `[data-darkmode]` 重复，删 | 18 |
| 208-224 | `body.nm-dark` 覆盖 | **D** | 自造主题检测，删 | 17 |
| 229-266 | 危险区 | **B** | 换 `.alert-message.danger` | 38 |
| 267-273 | `.nm-empty-state` | **B** | 换 `.alert-message.info` | 7 |
| 274-279 | `.nm-subsection-title` | **B** | 换 `h4` / `.cbi-section-descr` | 6 |
| 280-314 | `.nm-inline-setting` | **B** | 换 `.cbi-value` | 35 |
| 315-329 | `.nm-status-banner` | **B** | 换 `.alert-message` | 15 |
| 330-350 | `.nm-stats-grid` / `.nm-stat-card` | **C** | 保留（去 hex） | 21 |
| 352-422 | `.ys-tool-footer` | **A/D** | 整删 | 71 |
| 423-502 | 响应式表格第二段 | **A** | 删 | 80 |
| 523-727 | 文件浏览器布局/图标/路径栏 | **C** | 必要自定义，保留 | 0（保留） |
| 727-967 | 代码编辑器（4 套调色板：浅色 / media dark / `body.nm-dark` / 显式 light） | **C + D** | 保留结构，**合并为 1 套**并只留 light/dark 两个原生分支 | 120 |
| 969-1009 | 权限表 | **C/B** | 换 `.table` | 41 |
| 1010-1041 | 文件表 | **C/B** | 换 `.table` + `data-title` | 32 |
| 1042-1122 | 响应式表格第三段 | **A** | 删 | 81 |

**NGINX 小计**：A 7 项 / B 7 项 / C 6 项 / D 2 项；1123 行 → **约 300-450 行**（文件浏览器 + 编辑器是不可删的必要复杂度）。

> NGINX 的问题是「**一个插件里塞了两套设计系统**」：徽标/页脚/统计卡是插件的，文件浏览器/代码编辑器是自研 IDE 的，两者用不同的颜色来源，且都绕开了原生。

---

## 6. 跨仓汇总

| 仓库 | CSS 行数 | A 项 | B 项 | C 项 | D 项 | 预估剩余行数 | 削减比例 |
|---|---|---|---|---|---|---|---|
| performance-manager | 279 | 9 | 10 | 2 | 2 | 25-40 | **~88%** |
| upnp-nat-relay | 430 | 8 | 7 | 4 | 1 | 60-90 | ~82% |
| cloudflare-ip-r11 | 629 | 8 | 8 | 5 | 3 | 90-120 | ~83% |
| nginx-manager | 1123 | 7 | 7 | 6 | 2 | 300-450 | ~66% |
| **合计** | **2461** | **32** | **32** | **17** | **8** | **475-700** | **~76%** |

**改造后仍然允许存在的自定义 CSS，只剩三类**：
1. 结构化但原生没有的容器：统计卡网格、步骤条、折叠区、日志/代码区；
2. 文件浏览器的图标网格与路径栏（NGINX 独有）；
3. 代码编辑器的高亮配色（NGINX 独有，且应压缩为 2 套）。

其余全部应落到原生 class 上。

---

## 7. 原生样式白名单

### 7.1 允许使用的 class（附原生出处）

| class / 选择器 | 用途 | 原生出处 |
|---|---|---|
| `.cbi-map` + `h2[name="content"]` + `.cbi-map-descr` | 页面标题与描述 | `form.js` map 构造（`h2[name=content]` 是 `form.Map` 的标准标题） |
| `.cbi-section` + `h3` + `.cbi-section-descr` + `.cbi-section-node` | 区块/卡片 | `form.js` `AbstractSection` / `NamedSection` |
| `.cbi-value` / `.cbi-value-title` / `.cbi-value-field` / `.cbi-value-description` | 键值行/表单行 | `form.js` `NamedSection` 子节点 |
| `.cbi-page-actions` | 页面底部按钮区 | `luci.js` 的 apply/reset 容器 |
| `.cbi-section-actions` | 区块内操作按钮 | `form.js` |
| `.cbi-button` + `-positive/-negative/-action/-apply/-reset/-add/-remove/-edit/-reload` | 按钮 | 主题 CSS 与 `cbi.js` |
| `.label` + `.success/.warning/.notice/.important` | 状态徽标 | `admin/status/overview`、`admin/system/system` 的包状态、服务状态 |
| `.alert-message` + `.success/.info/.notice/.warning/.danger/.error` | 提示块 | `admin/network/network` 的接口提示、`system/reboot` 确认 |
| `.table` + `.tr/.td/.th` + **`data-title`** | 表格与窄屏堆叠 | `ui.Table` 写入 `data-title`，Aurora/bootstrap 都读 |
| `.cbi-section-table` / `-titles` / `-row` | CBI 表格 | `form.js` `TableSection` |
| `.cbi-tabmenu` / `.cbi-tab`（由 `ui.tabs` / `s.tab` 生成） | 内页标签 | `system/startup`、`status/routes`、`dashboard` |
| `.cbi-dynlist` / `.cbi-dropdown` / `.cbi-select` | 动态列表/下拉 | `form.js` `DynamicList`、`cbi.js` |
| `[data-darkmode="true"]` | 暗色分支（只读属性，不要自己加 class） | 两主题都支持 |
| `currentColor` / `inherit` | 自定义组件取色 | CSS 标准，非主题 |

### 7.2 允许使用的 CSS 变量

| 变量 | bootstrap | Aurora | 说明 |
|---|---|---|---|
| `--font-sans` | ✅ | ✅ | 唯一可安全引用的排版变量 |
| `--font-mono` | ✅ | ✅ | 代码区可用 |

**其余 71 个变量一律不得进入插件 CSS**，包括 PM 现在这套看起来很「跨主题」的 `--pm-*` 兜底链——它的 fallback 恰恰是硬编码色。

### 7.3 明确禁止

- 任何 `#hex` / `rgb()` / `rgba()` / `hsl()` 字面量（代码编辑器语法高亮是唯一例外，且必须收敛为 2 套）；
- `--main-color`、`--success-color`、`--warning-color`、`--danger-color`、`--subtext-color`、`--background-color`、`--background-color-a`、`--background-color-highest`、`--base-color`、`--cbi-background`、`--primary-color`；
- `cbi-map-title`、`cfi-*`、`nm-*`、`pm-*`、`ubr-*` 这类自造**布局** class（状态容器可保留命名，但必须无颜色）；
- `body.nm-dark` / `nm-light` 与 `detectLightMode()`；
- `data-label`（改装 `data-title`）；
- `#maincontent` 作为样式选择器（CF 状态横幅里有一处）。

---

## 8. 改造顺序与验证

排序原则：**影响面最大、改动最小、回归风险最低的先行**。

### 第 1 步：UPNP（1-2 个提交）

- 目标：删 `.ys-tool-footer`（118 行）、删两段响应式（126 行）、`.ubr-text-*` → `.label`/`.alert-message`、`data-label` → `data-title`、删 `.ubr-btn-group/.ubr-actions/.ubr-link`。
- 起点页面：`mappings`（表格最多，收益最直观）→ `overview`（状态横幅）→ `diagnostics`（日志区保留）。
- 为什么先做：结构已经原生（`form.Map` + `s.tab`），改完可直接当作另外三仓的模板。

### 第 2 步：CF（2-3 个提交）

- 目标：删 `:root` 的 `--cfi-*`、删 `@media`/`@container` 两段（207 行）、`.cfi-source-table` div 表格 → `<table class="table">`、`.cfi-badge` → `.label`、`.cfi-status-banner` → `.alert-message`、删 `.ys-tool-footer`。
- 起点页面：`sources`（div 表格 + 徽标，最能验证 `data-title` 契约）→ `diagnostics` → `overview`。

### 第 3 步：PM（2 个提交）

- 目标：改 `ui.js` 9 个 helper（`page/card/badge/kv/note/toolbar/field/inset/tableWrap`），一处改动覆盖 8 个 view；删 26 行 Aurora 预览块与整段 footer。
- 起点：先改 `page()` + `card()`，跑一次 `scripts/luci_render_smoke.js`，确认 8 个 view 都还能渲染。
- 注意：`pm-button--busy` 被 JS 切换，必须最后处理。

### 第 4 步：NGINX（4-5 个提交）

- 目标：先删 `.ys-tool-footer` + 三段响应式（232 行）；再 `.nm-badge` → `.label`；再删 `body.nm-dark` 与 `prefers-color-scheme` 两套；最后合并代码编辑器调色板（166 处 hex → ≤ 2 套）。
- 起点：`overview`、`logs`（结构性风险低）→ `sites` → `files`（文件浏览器，风险最高放最后）。

### 每一步的验证方式（四步通用）

1. **双主题基线截图**：在 bootstrap 25.12.5 与 Aurora 1.2.0 下，对同一页面在 360 / 768 / 1280 px 各截一张。
2. **与原生页对照**：把改造后的 `h2`、`.cbi-section`、`.cbi-button`、`.label` 的 computed `color/background/border-radius/font-size` 与 `admin/status/overview`、`admin/system/system` 的同类元素比对，**差值应为 0**。
3. **暗色跟随**：在 Aurora 里切换浅/暗（不刷新页面），自定义区域颜色必须同步变化；若不变，说明还在走 hex fallback。
4. **静态守卫**：`grep -nE '#[0-9a-fA-F]{3,8}\b|rgba?\(' <该仓>.css`，除以文件浏览器/编辑器外应为 0；`grep -n 'var(--'` 只应命中 `--font-sans/--font-mono`。
5. **窄屏标签**：把表格压到 360 px，确认每格上方出现列名（说明 `data-title` 生效）。
6. **冒烟**：跑仓库既有脚本（PM 有 `scripts/luci_render_smoke.js`），检查控制台无 `querySelector` 空引用、无 404。

---

## 9. 风险清单

| # | 风险 | 仓库 | 触发条件 | 严重度 | 规避 |
|---|---|---|---|---|---|
| 1 | 删 `.ubr-text-*` 会破坏 **98 处** JS 里拼接的 class | UPNP | 直接删 CSS 而不改 JS | **高** | 先改 JS 为 `.label`，再删 CSS；用 grep 收敛到 0 再动手 |
| 2 | `cfi-badge` 被 JS 用于状态渲染与选择器（23 处） | CF | 改 class 不同步 JS | **高** | 保留 `cfi-badge` 作为纯标记 class，只删其颜色规则 |
| 3 | `cfi-log-area`（17）、`cfi-table-wrap`（6）、`cfi-form-map`（6）被 `querySelector` 依赖 | CF | 删 class | **高** | 保留 class 名，去掉样式；或同步改 JS |
| 4 | `nm-log-area`（13）、`nm-badge`（10）、`nm-responsive-table`（4）被 JS 依赖 | NGINX | 同上 | **高** | 同上 |
| 5 | `body.nm-dark/nm-light` 删除后编辑器配色失效 | NGINX | 未改用 `[data-darkmode]` | 中 | 先加 `[data-darkmode="true"]` 分支，再删旧 class |
| 6 | `data-label` → `data-title` 不同步删响应式 CSS | 四仓 | 只改一半 | 中 | 同一次提交内改 JS + CSS；窄屏复测 |
| 7 | `pm-button--busy` 被 `ui.js:98,103` 切换 | PM | 删 CSS | 中 | 保留 2 行，或改 `aria-busy` + 原生 `:disabled` |
| 8 | 删 `.ys-tool-footer` 可能违背品牌展示需求 | 四仓 | 直接删 | 中 | 先确认产品需求；保留则去色，只留文本 |
| 9 | 把同级菜单合并成内页标签会改 URL | 四仓 | 做导航重构 | **高** | 本审计**不建议**在样式改造中做；单独排期 |
| 10 | 原生 `.label` 的形态与现有胶囊徽标不同 | 四仓 | 直接换 class | 低 | 视觉评审后再合并；可先用 `currentColor` 过渡 |
| 11 | bootstrap 的 `td[data-title]` 堆叠不如 Aurora 完整 | 四仓 | 只测 Aurora | 中 | 必须双主题各测一次窄屏 |
| 12 | `cbi-button-neutral` / `pre.errors` / `cbi-input-select` 只有单一主题支持 | NGINX | 沿用 | 低 | 换成 `cbi-button` / `.alert-message` / 原生 `select` |
| 13 | 未来 Aurora 若为这四仓加 patch，class 改名会失配 | 四仓 | 主题侧新增补丁 | 低 | 本审计建议的 class 均为原生，patch 应只依赖原生选择器 |
| 14 | 设备上 CF 部署版本比仓库旧，改动可能未生效 | CF | 只测设备 | 低 | 用仓库版本重新打包部署后再验证 |

---

## 10. 附录：本次实测证据

| 证据 | 位置 |
|---|---|
| OpenWrt 版本 | `.portable-rootfs/etc/openwrt_release` → 25.12.5 / r33051 |
| bootstrap 原生 CSS（77 个变量） | `.portable-rootfs/www/luci-static/bootstrap/cascade.css`（44 KB） |
| bootstrap 同时样式化 `.tabs` 与 `.cbi-tabmenu` | 同上，`.tabs,.cbi-tabmenu{...}` |
| bootstrap 样式化 `.btn` | 同上，`.item::after,.btn,.cbi-button{...}` |
| bootstrap 有 `--success-color-high` 但无 `--success-color` | 同上，变量表 |
| Aurora 1.2.0（166 个变量） | `main.css`（190 KB） |
| Aurora `.cbi-tabmenu` 药丸滑块 / `.tabs` 下划线 | 同上，规则原文见 §2 |
| 两主题变量交集 = `{--font-sans, --font-mono}` | 集合运算结果 |
| `cbi-map-title` 两主题均无定义 | 全文检索，0 命中 |
| `data-title` 两主题均支持 / `data-label` 均不支持 | 全文检索 |
| 主题渲染 `#tabmenu > ul.tabs` | `menu-aurora.js` `renderTabMenu`；`menu-bootstrap.js` 同 |
| 四仓 `menu.d` 均为同级子项 | 各仓 `root/usr/share/luci/menu.d/*.json` |
| UPNP 唯一使用 `s.tab()` | `network.js:243-244, 553-554` |
| 四仓 `data-label` 使用 54 处、`data-title` 0 处 | CF 11 / UPNP 16 / NGINX 27 / PM 0 |
| 四仓 CSS 规模与颜色计数 | 脚本统计（见 §6 表） |

---

*本报告为只读审计产物，未修改四个仓库的任何文件。*
