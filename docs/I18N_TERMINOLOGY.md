# 中文化术语对照与口径

本文件锁定性能管理器 LuCI 页面中容易混淆的术语。修改 `labels.js` 或 PO 时以本表为准；术语变更需同步更新本表与 `scripts/luci_render_smoke.js` 的断言。

## 核心对照表

| 英文（msgid） | 中文（zh_Hans） | 使用范围 | 理由 |
| --- | --- | --- | --- |
| Core | 核心引擎 | 指执行主体时（设置页分组、开关、说明） | `Core` 是确定性决策与执行引擎；直译成「核心」或「核心建议」会与建议对象混淆 |
| Core recommendation | 核心建议 | 指确定性建议对象时 | 与后端 `coreRecommendation` 字段一一对应，强调它是建议而非执行者 |
| execution authority | 执行权（最终执行权） | 安全模型说明 | 明确最终执行权始终在核心引擎，Rill 只排序 |
| Rill smart decisions | Rill 智能决策 | 功能名、页面标题 | 保留产品名 `Rill`，功能名统一为「智能决策」 |
| Rill Runtime | Rill 运行时 | 外部二进制、进程、状态 | 与「Rill 智能决策」区分：前者是运行环境，后者是功能 |
| benchmark / benchmark action | 性能测试 / 性能测试动作 | 全站 | 不再混用「基准测试」「检测」「测试项」 |
| companion test tool | 配套测试工具 | Benchmark 页 | 去掉 `Companion` 直译，说明其用途 |
| performance drift | 性能漂移 | 概览、Rill、设置 | 去掉「分布」，漂移是结果而非分布 |
| performance-x86 profile | 高性能（x86） | 设置页配置档 | 与 `labels.js` 的 profile 名称保持一致 |
| transaction / boot / decision identifier | 事务标识 / 启动标识 / 决策标识 | 历史、概览、Rill | 原始 UUID 仅用于日志关联，界面折叠到技术详情 |

## 口径规则

1. **执行主体永远是核心引擎。** Rill 只对核心引擎批准的操作排序；任何「由 Rill/核心建议执行」的表述都是错误。
2. **`Core` 与 `Core recommendation` 不得互换。** 前者是引擎，后者是建议对象。
3. **`Rill 运行时` 指进程/二进制，`Rill 智能决策` 指功能。** 不要用「运行时」指代整个页面。
4. **性能测试统一写作「性能测试」。** 包括动作、会话、阶段、证据与提供方，不再出现「基准测试」「检测」。
5. **标识不直接展示。** 事务、启动、决策、候选项 ID 在正文显示为「已记录，详见技术详情」，原始 UUID 保留在折叠的 JSON 中；不得出现 8 位截断 UUID。
6. **比例与单位。** 0–1 比例一律换算为百分比（>1 的收益同样按百分比）；设置页保留原始输入值，但说明中给出百分比/可读单位换算（如 `0.65` 表示 `65%`，`1048576` 字节/秒约合 `1 MiB/s`）。
7. **兜底必须可排查。** 未命中映射时显示「无法识别的状态，详见技术详情」或「未知操作/未知能力」，并保留折叠的原始响应，不得只显示裸枚举值。

## 维护入口

- 映射表：`package/luci-app-performance-manager/htdocs/luci-static/resources/performance-manager/labels.js`
- 翻译：`package/luci-app-performance-manager/po/zh_Hans/performance-manager.po` 与 `po/en/performance-manager.po`
- 断言：`scripts/luci_render_smoke.js`（枚举全集、折叠区、短 UUID、无点机器 ID、错误与空状态分支、设置页）
