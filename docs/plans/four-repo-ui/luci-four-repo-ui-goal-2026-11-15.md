# 四仓 LuCI 界面优化执行计划

将下段作为 Goal 的目标，执行时读取整份文件。

> 按以下顺序执行，当前阶段不得越序：**1) 先完成性能管理器八页的普通用户友好化、跨主题响应式审阅、GitHub Actions 候选包构建和本地 OpenWrt 实机验收；2) 再完成通用 Rill OpenWrt runtime 接入，使性能管理器和 Cloudflare IP 调用同一个消费者无关的 Runtime；3) 最后完成四仓库 32 个独立视图的完整视觉基线、修复、构建和装机验收。** 每阶段保留分仓证据、构建链接、包校验值和设备恢复记录。所有必测项通过后才标记 Goal 完成。发布、打标签和合并由用户另行决定。

## 1. 当前基线与审计判断

2026-11-15 只读核对。四个工作区干净。执行时重新记录当前 HEAD 与远端，保留用户已有改动。

| 仓库 | 当前分支及 HEAD | 路由根目录及独立视图 |
|---|---|---|
| luci-app-cloudflare-ip | `fix/ui-spacing` · `480546b` | `admin/services/cf_ip` 下的 `overview`、`settings`、`advanced`、`sources`、`intelligence`、`logs`（diagnostics）、`openclash`、`passwall` |
| luci-app-nginx-manager | `fix/footer-full-version` · `fd36ba1` | `admin/services/nginx-manager` 下的 `overview`、`sites`、`sites/edit`、`certificates`、`files`、`core-config`、`backups`、`logs`。另测根入口，注意编辑页没有菜单标题 |
| luci-app-performance-manager | `fix/footer-full-version` · `fbb7b65` | `admin/network/performance-manager` 下的 `overview`、`optimize`、`benchmark`、`capabilities`、`rill`、`history`、`settings`、`advanced` |
| luci-app-upnp-nat-relay | `fix/footer-full-version` · `8504284` | `admin/services/upnp_nat_relay` 下的 `overview`、`wizard`、`settings`、`network`、`security`、`mappings`、`openclash`、`diagnostics` |

本地 `openwrt` 可通过 SSH 访问，运行 OpenWrt 25.12.5 x86/64，使用 apk。已装 Cloudflare IP 2.6.2-r1（另有 Rill）、Nginx Manager 1.8.11-r1、Performance Manager 1.0.7-r1、UPnP NAT Relay 1.3.16-r1。当前主题 Aurora。设备有 Bootstrap、Bootstrap Dark、Bootstrap Light 及 Aurora 资源目录。Argon 有 UCI 条目，设备主题目录清单里没有对应资源。执行时核实各主题包、对应 CSS 和实际浏览器加载结果。以安装且实际可用的主题作必测；已声明支持的额外主题按其支持承诺纳入独立测试实例。

- **UPnP 日志页旧观察已复核并关闭。** 当前 exact source `026b95d` 的 `diagnostics.js` 设置 `handleSave`、`handleSaveApply`、`handleReset` 均为 `null`；设备实际加载的 JS SHA-256 与该文件一致。固定同一日志页与空日志状态，Aurora Light/Dark 与 Bootstrap Light/Dark 的 320px 矩阵截图均未显示默认保存栏；设备 Aurora Dark 桌面实机检查同样未显示。只保留页面自有的筛选、刷新、清理、回滚按钮。旧记录中的“多出默认保存栏”属于过期基线观察，不是当前候选缺陷。
- **源码确认，浮动工具栏避让覆盖范围不同。** 四仓均有 1319px 附近的 Aurora 兼容规则。Cloudflare IP 额外覆盖日志控件，Nginx 覆盖文件及行内操作，Performance Manager 的当前规则集更短。逐页检查实际命中、浮动栏展开／收起、页面滚动和弹窗。已解决的遮挡用截图防回归，复现的问题修在相关组件。
- **源码确认，响应点分布不同。** 四仓都包含 600px、48rem、1319px 附近规则，Cloudflare IP 还含 420px、700px、1048px，Nginx 含 700px、1048px，UPnP 含 700px。结合设备实际主题和运行时内容重新提取完整断点。旧的同类计划可用于定位脚本，里面的历史截图、行号和删改建议需基于当前代码重新验证。

## 2. 先拿完整视觉基线

1. 以每仓 `menu.d` 和 `view/` 为入口，追踪 JS 模块、`tab()`、模态框、Wizard 步骤、详情路由、内联展开、ACL 和依赖条件。把菜单、直接链接、别名及隐藏入口对应起来。记录覆盖矩阵的行数和来源，新增覆盖项时同步更新回归清单。
2. 本地装机包与源码 HEAD 的对应关系尚未证明。先记录设备包信息和已安装资源的哈希，建立当前设备参考截图。若对应关系不同，在隔离实例安装对应基线包，记录准确 commit、产物和主题版本后再作同位置比较。
3. 从浏览器会话按页面打开并取基线。保留页面全图及折叠前后、底部、浮层等容易漏检的位置。读取实际加载的主题 CSS、插件 CSS 及媒体／容器查询，包括 min/max、重叠规则、字体单位和 JS 断点。断点清单包含触发条件、适用页面和坐标轴。
4. 从原生 LuCI 同类型页面核对表单、表格、按钮、标签、通知和焦点行为。对每项记录截图、复现步骤、实际影响、涉及的组件及预期结果。按操作被遮挡／误触／无法完成、布局或语义不清、纯细节依次处理。

## 3. 改动顺序与每仓重点

先在四仓各取一个代表性页面核对共同规则，再按仓完成各自页面。按钮默认遵从真实操作对象和 LuCI 按钮语义。页面保存、区块动作、行内动作分放在其作用范围中。宽屏就近对齐，窄屏按原 DOM 和键盘顺序换行。危险操作与高频刷新、筛选保持可辨识。对重复标题、空容器、重复分隔线、占位和默认按钮，先确认用户任务与 handler 再决定去留。

优先复用实际支持的 `form`、`ui`、CBI 结构和对应主题提供的外观。需要保留编辑器、日志区、数据网格、品牌页脚和主题避让时，把自定义规则限制到相关组件，并在改动记录写明原生结构无法覆盖的具体行为。保留版本与链接的信息和可访问名称。以跨主题截图决定兼容规则，避免一次性重写或按历史 CSS 白名单批量删除。

| 仓库 | 应重点演练的流程与状态 |
|---|---|
| Cloudflare IP | overview 的运行／停止及加载反馈，settings/advanced 的保存和校验，sources 的空／多条来源及编辑，intelligence 的 Rill 可用／不可用，logs 的筛选及长记录，OpenClash／PassWall 的依赖缺失和接入后的表单 |
| Nginx Manager | 站点列表、创建与编辑两个分支，证书列表与配置弹窗，文件目录和编辑器、长路径，核心配置的保存与校验，备份及恢复确认，日志筛选与长日志。重点看表格行末、对话框底部和 Aurora 浮动栏 |
| Performance Manager | 总览、优化操作与结果、基准测试待机／运行／结果、能力支持／缺失、Rill 状态、历史空态／回滚、设置及高级表单。检查卡片密度、长值、状态更新和操作归属。在隔离环境演练真实优化或回滚 |
| UPnP NAT Relay | 向导每步及返回／取消，设置／网络／安全的依赖字段和保存，映射表数据与空态，OpenClash 依赖分支，日志筛选和清理确认。检查即时动作与待保存配置的归属 |

改造涉及 DOM 移动、禁用或移除控件、改标签、改表格渲染时，核对事件、RPC、ACL、UCI 读写、轮询和中英文目录。运行各仓已有的语法、i18n、合同及回归检查。按需要增加能复现具体回归的检查。

## 4. 必测矩阵与通过标准

- **主题与语言。** 必测 Aurora 浅色与暗色、Bootstrap 默认与显式 Light/Dark（按实际主题能力记录默认模式、系统跟随及探测结果），中文和英文。通过原生主题选项切换并刷新复测，记录实际样式 URL、模式及主题状态。Aurora 浮动栏视觉有影响的页面测展开、收起、滚动时遮挡。
- **主题归因边界（用户确认）。** 原生 LuCI 控件和 `.cbi-page-actions` 等标准结构由当前主题决定外观；不按主题名覆盖颜色、按钮尺寸、警告框、下拉框、模态框或原生工具栏。主题本身的缺陷留作主题记录。只有插件自有标记、自定义组件、插件 CSS 或违反 LuCI 响应式标记契约导致的失败才在插件内修复；遇到混合问题只修通用的插件组件行为。诊断时固定页面、数据、语言、明暗、视口和交互状态切换主题，检查实际加载的 CSS、DOM 与 computed style 的获胜规则，并在适用时和原生 LuCI 同类控件交叉验证。Vantage 是用户授权的归因探针；其单页比对不扩展正式六种主题矩阵。
- **宽度。** 常用 CSS 视口宽度选 320、360、390、430、768、1024、1280、1440、1920。再对每个实际相关断点跑 `b−1、b、b+1`，去重。已知待核对边界包括 375（设备宽度）、420、600、700、48rem/768、1048、1319/1320。容器查询按实际容器宽度测试，设备宽度／触摸媒体查询用匹配的设备配置。移动端测短视口、竖屏和横屏，重点查底部、模态可滚动和移动菜单。
- **全覆盖。** 每个独立视图的每个可见布局状态，覆盖主题模式 × 两语言 × 对其生效的常用宽度及断点邻值。可见布局状态包括主要子页签、向导步骤、弹窗、展开行、依赖分支、加载和禁用、错误、空／有数据、长内容等。只合并经比对确为同布局同语义的状态，并记录依据；不存在的组合由代码或实机证明。别名、根入口和隐藏详情需要路由到达验证。真实业务交互至少在标准桌面和最窄适用视口完成；其他宽度覆盖同一交互控件可达、状态完整及截图可读。
- **截图和交互。** 使用同样主题、语言、宽高、数据与状态做前后对比。可用现有浏览器测试脚本批量取图和测量，逐状态打开足够分辨率的图片审阅，缩略图只作索引。截图中检查分组、间距、对齐、换行、表头和数据关系、按钮断行、文本和图标、浮层与页脚；额外逐项检查按钮和相邻字段／行是否零间距或视觉粘连、相关控件是否清楚分组、同类状态块是否采用一致的 LuCI 原生结构。宽屏将可并列的相关控件同组排列，窄屏堆叠时保留明确的行距；原生间距交由主题，插件只修自身生成的布局。浏览器额外验证焦点可见、顺序、弹窗开关和焦点恢复、按钮可点击、状态变更和长内容访问。无页面级意外横滚，无可操作控件被裁切或遮挡，无重复或无效的默认操作栏，组件内部必要的滚动可操作。
- **间距判断（用户补充）。** 状态区上下留白不要求像素完全相等；尽量复用 LuCI 原生样式，达到视觉上大致均衡即可。以完整截图人工判断是否仍明显一边松、一边紧；DOM 文本／边界测量用于定位和辅助对比，不把零差或固定像素差当作唯一通过门槛。不得为消除细小差异破坏主题原生卡片、边框和排版。
- **共享页脚背景块（用户补充）。** 品牌标记和项目／社交链接的背景应贴近文字与图标，上下留白收紧，并在四仓保持一致；链接仍保留清楚、足够大的点击区域。人工复核中文／英文、所有可用主题模式、短视口与页脚相关断点。
- **性能管理器全页样式对齐（用户授权）。** 八个视图都对照另外三个插件统一到相同的 LuCI 阅读和布局规则：标题／说明、状态提示、摘要／信息分组、相关内容并排、操作靠近对象、技术详情收纳。优先使用主题原生 `alert-message`、`cbi-section`、表格、表单、标签和按钮；通用响应式网格只负责分组排列，主题继续控制表面与控件外观。逐页删除确认为冗余的标题／字段重复、空状态信息块和无效网格容器；保留所有既有数据、交互、技术详情折叠与路由。覆盖两种语言、六个主题模式、320px 起的有效断点、空／有数据、加载／错误、长值与展开状态，并在最终候选 APK 的本地设备上回看。
- **性能管理器普通用户信息架构（用户补充）。** 八个视图以普通路由器用户的任务为默认阅读顺序：先看到运行状态、安全状态、当前建议／测试／可执行操作及其影响；常见功能设置保持直达。置信度、学习进度、排名、测量结果等能帮助理解决策的少量进阶信息可继续直接查看。提供方／协议／内部 ID、原始契约、候选历史、详细测量阈值等高密度诊断项收在原生折叠详情或专门的 Advanced 页。仅在确认无独立用户任务、已被更清晰信息完整替代且仍能从高级详情追溯时，才隐藏重复或不必要的内容。不得丢弃现有可用配置、必要安全状态、失败原因、回滚确认或高级用户查验数据。设置分组优先用设备所运行 LuCI `form.js` 支持的原生 section/tab API；最终逐页验证中英文及可用主题下的主次顺序、折叠可见性和保存行为。
- **逐行记录。** 记录仓库、路由／子状态、主题模式、语言、宽高、容器宽度（适用时）、数据情景、commit、设备／包版本、截图、结果和复测编号。结果用 PASS／FAIL／BLOCKED／N/A，N/A 附依据。用清单生成预期行并与截图及审阅结果对账，所有必测行都有 PASS 和可打开的证据才能收尾。修共同 CSS 或公共渲染器时重跑其所有消费页面，并在最终候选包上完成全量验证。

## 5. GitHub Actions 构建与本地安装

| 仓库 | 优先入口 |
|---|---|
| Cloudflare IP | `.github/workflows/ci.yml` 有 25.12.5 x86_64 的 SDK APK 构建。另跑 `real-luci-ui.yml`，它当前覆盖的 24.10.8 Bootstrap 环境可提供额外回归证据 |
| Nginx Manager | `.github/workflows/pr-build.yml` 上传 APK/IPK，当前 25.12 SDK 项为 v25.12.0。先验包与设备兼容，遇依赖不符时按设备目标构建 |
| Performance Manager | `.github/workflows/build-openwrt.yml` 支持 PR 和手动触发，选适配 x86/64 的 APK 和实际所需依赖 |
| UPnP NAT Relay | `.github/workflows/release.yml` 手动触发，显式传 `publish=false`。当前发布参数默认开启，调用前核对 job 条件 |

1. 各仓使用验证分支保留基线。使用构建所需的分支推送、手动触发或 PR 检查入口。跟到对应 SHA 的 Actions 结束。记录 repo、SHA、run ID/attempt、artifact、目标架构、包名和 SHA-256。下载候选产物并校验。CI 产物缺失或失败时追查原因、修复并取得新行的成功记录。
2. 记录现有包、依赖、插件 UCI、主题和服务状态。准备可恢复的 VM 快照或配套原包与配置备份。先在隔离 OpenWrt 验证包升级、依赖、配置及可恢复性，使用独立测试配置演练改写 nginx、OpenClash、PassWall、nftables、系统性能和回滚等操作。
3. 从这批 Actions 产物逐仓安装到本地 OpenWrt，核对已加载的资源与包一致，用独立浏览器配置或清除对应静态缓存消除旧资源干扰。四仓候选包共存时复核共用主题、语言、导航与页脚。设备为日常路由时，把需要改变运行状态的场景放在本地隔离实例上，使用同一批 APK 和同版本主题。结束时恢复测试数据、主题及临时设置，记录候选包或回退包的实际留存状态。

## 6. Goal 完成条件

- 四仓交付分仓变更摘要和候选提交，列出对应 Actions 成功运行和 APK 校验值。
- 本地 OpenWrt 装机记录绑定同一批产物。输出可打开的截图索引、前后图和必测矩阵，覆盖所有仓、页面、适用状态、主题模式、语言和断点。
- 代码检查及交互回归通过。逐条消除必测 FAIL／BLOCKED；真正不可达的组合有可复核的 N/A 依据。遇到设备／依赖障碍，先在同目标系统的隔离实例补出场景，有实质阻碍时保留复现记录和恢复信息，由 Goal 继续追踪。

## 执行状态更新（2026-11-17）

顺序按用户澄清保持：性能管理器界面 → 通用 Rill OpenWrt → 四仓库完整视觉优化。

- **阶段 1 性能管理器界面：PASS。** exact UI 候选 `6ee505d667046a520478126094629cfeb997237d` 的 UI-only APK 由 Actions run `44046236735` 构建并装入 OpenWrt 25.12.5 x86/64。配置哈希和服务状态保持。Vantage/Aurora 实机页面审阅记录见 evidence 文件。另在真实 LuCI/Chromium 执行中英文矩阵：英文 run `44059267133` job en 成功；中文 run `44066294565` zh_cn 成功；各 1,968/1,968 PASS，覆盖 8 页、6 种主题模式、39 宽度和横竖短视口。所有 contact sheets 已人工审阅，无插件导致的溢出、重叠、裁切或断点异常。详见 `luci-four-repo-ui-evidence-2026-11-15/pm-final-phase-6ee505d-2026-11-17.md` 与各 run evidence 目录。
- PM workflow guard commit `7a870ef855ea587de883dc7b8490d71e84de955d` 让依赖安装具备网络诊断与超时；首次组合 run 的中文 job 卡在依赖安装，已取消，zh-only rerun 成功。
- 多架构 build run `44059267055` 的 Core 与 LuCI 编译通过，但到 `Build Rill integration package (glue payload only)` 失败。这归入阶段 2 的通用 Rill 契约/构建缺陷，不回退阶段 1 已验证的 UI-only 候选包。阶段 2 完成后需重新运行对应 PM build 验证。
- 当前执行下一步为 **阶段 2 通用 Rill OpenWrt runtime 接入**。明确 Rill OpenWrt 是消费者无关的 runtime/provider；性能管理器与 Cloudflare IP 作为消费者共用公共接口，Rill 仓库不得硬编码服务这两个插件。

### 阶段 2 进展（2026-11-17）

- PM 多架构构建缺陷已修复：`build-openwrt.yml` 不再把 Rill Stable 源码配方复制进 PM SDK，避免 SDK 因依赖关系重复下载并构建 provider，直接消费资格化 Runtime APK。候选 `41672ad2df1c71e622bd994b00d4331a863e4208` 的 Actions run `44071903519` 三个架构全部成功；CI run `44071903408` 中静态、真实 Runtime v3 子进程和生产核心集成均通过。APK SHA、runtime payload SHA 和构建证据见 `luci-four-repo-ui-evidence-2026-11-15/rill-phase-2-2026-11-17.md`。
- provider 中 Preview 描述泛化候选 `e689db01114acfb661059f5576f1c5b2f0c7dfb07` 尚未合格或发布。qualification run `44071932185` 正确挡住 Stable `v1.5.6` tag 已漂移的情况：现在 tag 指向 `7f2062b9a3fad5be8e4defb14f29442d3044aa13` / archive SHA `beee3413ae3d187aef3d4c446af478e82695032e6529fe233b80caa998b87fda`，而已 pin/资格化 Stable 仍为 commit `b990cd7043d313b0ff29c9693f091a94a5bdaf47` / SHA `c06a792811d1f08aa7b640c10ee36047c44f825cf7272aa0f75c42ab60806a84`。不允许同一已发布 SemVer 静默换源。
- **阶段 2 同机共存要求已确认。** 用户要求 PM 和 CFI 的 Rill 功能必须能在同一台 OpenWrt 同时运行。当前 PM split 包依赖 Stable `rill-runtime`，CFI 依赖互斥的 `rill-runtime-preview`；PM All-in-One 还物理拥有 `/usr/bin/rill-runtime`，并排斥 Preview。不能仅删除冲突声明，否则会出现同路径双包所有权和运行时通道漂移。
- **阶段 2 执行方向。** 统一两个消费者实际使用的 v3 Runtime 包为同一份 exact-qualified、消费者无关的 Preview Runtime。PM split 包依赖该包；PM All-in-One 必须以可验证的共享包所有权方式满足该依赖，不得覆盖/重复占有其文件；CFI 继续依赖同一个包。Rill OpenWrt 保持通用，不增加 PM/CFI 服务、配置、RPC 或插件特定逻辑。Stable 渠道继续独立资格化和保留，不能与共用 Preview 同时安装。对两消费者做同机安装与真实协议调用后才验收阶段 2，再进入阶段 3。
- **阶段 2 构建修复进行中。** CFI `.github/workflows/ci.yml` 已移除其构建矩阵中未被 CFI 消费的 Stable package 配方，保留 exact Preview 包验证；该工作流改动尚未提交或取得新 CI 结果。接下来需要完成 PM split/All-in-One 的共用包所有权及契约迁移，重跑 CFI/PM Actions，安装同一批 exact artifacts 并在设备验证两个插件的 Rill 状态。
- **阶段 2 共享包迁移已落到候选源码（验证未完成）。** PM split 与 All-in-One 改为依赖 `rill-runtime-preview`，不再拥有 `/usr/bin/rill-runtime`；证据、发布说明、升级门禁、Docker 路径和同一包所有权探针同步迁移。PM 与 CFI 的 CI 都只消费 Preview provider。PM 静态合同通过，除依赖干净 worktree 的发布模拟外 184 个 Python 用例通过；Actions 与设备同机验证尚待新 commit。Provider 当前仅有资格证据的版本仍为 `rill-runtime-preview 1.5.6-r6`（package commit `0567336…`，qualification run `42169166493`）；消费者无关描述候选 `e689db0…` 尚未资格化，且之前被 Stable 上游标签漂移门禁挡住。当前不把未资格化 package release 7 纳入消费者锁，也不把阶段 2 记为完成。


### 阶段 2 最终验收（2026-11-17）

- **阶段 2：PASS，允许进入阶段 3。** PM 候选提交 `0e3ae2b39903b505700aa3b345d84b454c86f0cb` 的 Actions 多架构构建 run `44093312848` 已完成成功，x86/64、armv8 与 MTK Filogic 均成功；对应 CI run `44093313373` 成功。最终 x86 All-in-One APK SHA-256 为 `65c1fa242cf3eb437bc452b7a8a76e73da6539c7c5bcf2b843f9670c9f9396ae`，设备实装版本 1.0.7-r1。产物清单和同机诊断见 `luci-four-repo-ui-evidence-2026-11-15/rill-phase-2-2026-11-17/`。
- 精确资格化且通用的共享 provider 仍为 `rill-runtime-preview 1.5.6-r6`，文件所有权唯一；设备 `/usr/bin/rill-runtime` SHA-256 `c3ad43ed73cc7b57dbc3835ea01f8b6ff03d69ab213655b72c60e25f05f96abe`。PM 状态为 enabled/available/compatible、API v3、model health healthy；CFI 同时通过其只读 v3 self-check，状态 healthy。
- 设备现存 PM/CFI 配置哈希恢复并与原值一致：`performance-manager` `19bf0cd88577fca49e0902633d0fc8a38beb480ae1297d00433b888c1da1a505`；`cf_ip` `2591b0cb3d332d8b0f8a6be059cf7f2160f4409cef115935c6d28c6a73d93751`。PM 页面实机确认显示“RILL 运行时可用”。同机调用及恢复记录见 `rill-phase-2-2026-11-17/same-device-pm-cfi-rill.txt`。
- CFI 消费者 CI run `44091182103`（commit `177d7c72336851a1a16c382d807c515469c4dd68`）成功。provider 代码及其正式发布范围未扩大，未发布或合并未资格化的描述候选。
- **阶段 3 已开始。** 四仓当前 HEAD：CFI `177d7c72336851a1a16c382d807c515469c4dd68`；Nginx `6704d9615313d085f576134e94b079c88094f944`；PM `0e3ae2b39903b505700aa3b345d84b454c86f0cb`；UPnP `1c5ea8487a615534cdcab717ebab6c3c7a169dc2`。已有矩阵可以复用作基线索引，但不自动等同于这些当前 HEAD 的验收：按 commit 逐行核对，不同源码或截图夹具须重拍和复审。已知前轮 CFI/PM 中文与集成视图、UPnP 英文以及四仓页脚提交后的精确来源截图仍有待收尾；阶段 3 通过条件仍是全部适用视图、状态、主题、语言、断点及实机/构建证据均 PASS 或有明确依据的 N/A。

### 阶段 3 更新（2026-11-18）：页脚对齐已完成，整体验收继续

- 用户要求以性能管理器页脚为参照，完成 CFI、Nginx、UPnP 三仓对齐。三仓仍使用统一的 LuCI 主题样式和相同 footer 结构；设备验证通过 `ui=footer-pm-match-1` 强制加载候选 CSS，实时几何与 PM 参考相同，社交背景完整包含图标及文字。三包已从对应 Actions 构建产物 force-reinstall 到 OpenWrt 25.12.5，主题和插件配置、服务状态未发生意外变化。具体产物与哈希见 `luci-four-repo-ui-evidence-2026-11-15/footer-final/device-footer-alignment-2026-11-18.md`。
- 页脚 exact-source 检查已覆盖 CFI `b045520…` 英／中文主矩阵及安装代理矩阵（每语言 1,830 + 462 行）、Nginx `b23dfcc…` 英／中文（每语言 1,734 行）、UPnP `b2cb6cb…` 英／中文（每语言 1,686 行）。共 11,424 行（10,512 PASS、912 有依据的 N/A），零自动化错误，所有行均验证新 CSS URL 和 PM 页脚几何。三仓对应的六主题截图已复核；细节记录和联系表位于 `footer-final/`。
- UPnP 的临时验证分支 `codex/footer-matrix-retry-2026-11-18` 在同 SHA 英中运行都成功后已删除。
- PM 当前 exact-source 页面门禁 run `44132092398`，SHA `0e3ae2b39903b505700aa3b345d84b454c86f0cb`，后续终止为依赖安装失败。修复网络后的双语 run `44143052364` 已完成：英文、中文各 1,968/1,968 PASS、零错误。两种语言的 1,968 张当前图像都在 y=60 以下与已审阅对照图像素完全一致；逐行复核在 `luci-four-repo-ui-evidence-2026-11-15/pm-run-44143052364-a8-en-pixel-review.csv` 和 `pm-run-44143052364-a8-zh-pixel-review.csv`。本地 OpenWrt 24.10.8/real LuCI 中文补充矩阵在安装 checksum-pinned Aurora 后也完成 1,968/1,968 PASS、零错误，详情 `pm-0e-local-zh-rerun-20261118/local-validation.md`。保持本 Goal active，继续完成剩余视图适用状态的截图、人工审阅、设备和构建证据；页脚子项 PASS 不代表阶段 3 或 Goal PASS。

### PM 当前 OpenWrt 补充实机审计（2026-11-18）

- 按用户建议，将正在运行的 OpenWrt 作为 PM 的真实运行与视觉审计来源之一。设备当前 LuCI 设置页显示 Performance Manager `1.0.7-r1`，Aurora Dark、中文；8 个页面此前均已只读复核。本次补充检查设置页：内核与通用 Rill 运行时分组间距明确，表单项的标签、控件和说明层级可读，Rill 通用二进制路径正常显示，页脚按钮可访问。
- 该设备上 Aurora 悬浮快捷工具条与原生 LuCI 底部操作栏发生边缘覆盖。此覆盖不由 PM 页面 CSS 控制，归类为主题/原生覆盖层问题；遵循用户约束，不为主题自身问题增加插件补丁。
- 当前设备复核限只读页面。性能测试、回滚、自动化建议应用、设置保存等有副作用的状态继续要求隔离测试实例/独立测试数据；不得仅为截图在日常运行设备上触发。
- 额外完成一次低风险的 PM 实机业务状态核对：仅启动“仅健康检查”，没有运行受控 A/B 或网络性能测量。六阶段状态全部完成，页面清楚标注“已采集健康状态；这不是性能测试结果”；会话 JSON 的 `measurementClass=health_only`、`state=completed`、`changedSystemState=false`，前后快照相同。该动作留下一个健康检查会话记录，但未应用系统参数、保存设置或重启服务。结果区和折叠的高级 JSON 在当前主题下层次清晰；未发现此状态下 PM 内容溢出或控件粘连。

### 阶段 3 当前 CFI 中文复核补充（2026-11-18）

- CFI 当前 exact source `b0455209740c14528a610d0c7e248b63c8955807` 中文 run `44123328312` 的全量截图已下载并逐行绑定审阅台账：主矩阵 1,374 PASS + 456 个有依据的可选集成入口 N/A；安装 OpenClash/PassWall 矩阵 462 PASS；零自动化错误、零待审行。台账：`luci-four-repo-ui-evidence-2026-11-15/cfi-run-44123328312-b045-zh-review.csv` 与 `cfi-run-44123328312-b045-zh-proxy-review.csv`。
- 这个 SHA 相对此前全量人工审阅的 CFI 基线只改了共享页脚背景/尺寸以及概览状态块间距。当前中文截图在窄屏、导航转换与宽屏（Aurora Light 320/768、Aurora Dark 1920）复核后，概览间距约与主题原生节奏均衡；OpenClash 320×568 页面表单、长说明、备份告警、页脚与保存操作均可滚动到达。每行自动门禁确认无溢出且页脚几何匹配 PM；精确源码六主题页脚截图另有人工复核。此前 11,424 行页脚汇总不变。

### 阶段 3 当前 Nginx 文件页复核补充（2026-11-18）

- Nginx 当前 exact source `b23dfcc90b1deda40dc29fbe47681c289b65fbfc` 中英文 Real LuCI UI Gate 分别为 `44116014898`、`44120276958`；每语言 1,734/1,734 自动 PASS、零错误。已下载全量图并为文件页单独生成六主题、每语言 216 行的逐宽度联系表，覆盖 320px 起的常用宽度、每个实际响应边界邻值、320×568 与 568×320。中英文文件页全矩阵人工检查通过；在 320px Aurora Light 页面另行检查了长文件列表、工具栏、行操作和页脚。载入后的“14 项”不再显示，工具栏后直接进入文件表格，状态节点仅在加载时按需呈现并关联表格；横向滚动区、表头和操作仍清晰。
- 当前行级台账：`nginx-run-44116014898-b23-en-b23-review.csv` 和 `nginx-run-44120276958-b23-zh-cn-b23-review.csv`，各绑定 1,734 张 exact-source 截图，无待审行。Nginx 余下未覆盖项以交互／业务状态为主：真实新增／编辑／删除、有效证书与 ACME 成功、完整备份恢复流程以及装机后交互。全页面首次态截图 PASS 不能替代这些状态验收。
- 实机补充：本地 OpenWrt 25.12.5 已安装 Nginx Manager `1.8.11-r22`。在中文文件页确认真实目录的 14 条目仍在、父目录导航仍单列，已加载目录没有“14 项”悬空文案。打开并取消新建文件、新建目录、改名和删除确认对话框，未创建、改名或删除任何文件。最终包界面状态与当前截图修订一致；剩余真实交互重点仍为站点编辑/保存、证书与备份生命周期和其他各仓列出的专项状态。

### 阶段 3 当前 UPnP 安全向导实机补充（2026-11-18）

- 在本地 OpenWrt 25.12.5 已安装的 UPnP NAT Relay 页面中，中文逐步走查安全向导全部 10 步。确认字段布局、校验/提示、只读连通性检测、已发现映射和最终配置预览均可读、操作顺序清楚。最终保存按钮未按下；没有应用网络或服务配置。返回概览后现有 UPnP 服务仍显示运行中。
- 该证据只覆盖安全模式导航和只读检查。自动模式、真实配置变更以及有内容的诊断日志仍需在隔离环境继续验收，不能据此关闭 UPnP 交互状态门禁。

### 阶段 3 当前继续项（2026-11-18）

- **PM 概览首状态块已修正并实机复核。** 提交 `4f3b892f10c206477a349b0674a51d4b9345959c` 将 PM 状态块容器补为与 Nginx、CFI、UPnP 一致的 LuCI 原生 `cbi-section alert-message`，更新 CSS 缓存键；未增加主题专用 CSS。CI `44172512827`、LuCI UI SDK 构建 `44172512825` 和多架构 All-in-One 构建 `44172513212` 均成功。x86_64 APK SHA-256 `c9bc9b7adb8107183e987738c7334b2dee6476f127e50c0b0c68f1e94849e4e1` 已装入 OpenWrt 25.12.5；Aurora Dark 中文桌面截图确认灰色原生区块、标题分隔线和边界已与其余插件一致，PM/LuCI 配置哈希不变。精确双语真实 LuCI 矩阵 `44172512963` 仍在运行，完成后还须按结果补全截图审阅记录。
- **UPnP 概览依赖标题已修正并实机复核。** 在 exact-source 英文窄屏截图发现普通健康状态仍配“Missing Dependencies & Fix Commands”标题，提交 `4358c51fea94e7aed991ff1debb0842f3dfa65fe` 改为中性 `Dependency Status`，更新英文／中文 PO 与视觉门禁断言。Node、shell、PO 和 diff 检查通过。Actions 非发布 SDK 构建 `44174823870`（手动传 `publish=false`）的 APK 与 IPK 目标成功，发布 job 按要求跳过；25.12 x86_64 APK SHA-256 为 `b3e67ec3d29b1bfcf761a4e73f5d971dc0d05b171bffdd601086e81d18e6a6dd`，已安装本机 OpenWrt。overview.js 设备哈希匹配源码，UPnP 配置哈希不变且服务仍运行；Aurora Dark 中文实机截图确认“依赖状态”与“所有依赖已安装”语义吻合。真实 LuCI 矩阵 `44174806960` 英文成功，中文 job 在依赖安装步骤持续运行至整 job 结束（step 仍标记 in progress，日志暂不可取）；失败发生在截图捕获前，因此不能当作 UI 失败或视觉 PASS。需要修复/重跑中文 job，再审阅 exact-source 全量截图。
- 上述页面修正不关闭四仓 32 视图的全量子状态、主题、语言、断点和交互验收。阶段 3 Goal 保持 active。

### PM 页面体验优化实机补充（2026-11-18）

- 用户建议把当前运行的 OpenWrt PM 纳入审计。本轮在 OpenWrt 25.12.5、LuCI 25.12.5、Aurora Dark 中文、Edge 约 1298×768 视口中检查最终候选 `a31feb46d369356709d4bab93839901a0f0a8090` 的八页：概况、智能优化、性能测试、能力、Rill 智能、历史与回滚、高级、设置。八页均加载成功并呈现设备真实数据；PM 设置、LuCI 设置与 Rill runtime 文件哈希保持不变。此前因 ubus 对象缺失而超时的 Rill/历史/高级页面，在安装该候选并重载 PM 服务后可读取数据。
- 概况已确认标题下不再渲染字面 `null`，首个状态块采用与其他插件相同的 LuCI 原生状态区块；性能测试控件呈两列分组，桌面视口下动作/路径与测量类型/开始操作成组；高级首屏展示服务、配置方案、健康保护、自动化模式及资源占用，技术诊断折叠；Rill 首屏显示运行状态、建议、排名和解释，历史首屏显示事务并把锁/事件历史折叠。能力页各状态卡和设置页 CBI 表单在设备主题下可读，未见布局溢出或主题自定义色覆盖。历史页存在真实“回滚”操作，检查时未触发；未修改设置、运行基准测试或触发 Rill 刷新。
- 精确候选包来源于 All-in-One Actions run `44185758580`，设备安装包 SHA-256 `b17bf2df292927fe4f18c805b412ffa2a72b3cc5285db0df537d3e720b75d311`。精确 SHA CI `44185758651`、LuCI UI SDK 构建 `44185758624`、OpenWrt 多架构构建 `44185758580` 均成功。真实 LuCI UI Gate `44185758570` 本记录时英文视图矩阵仍运行、中文 job 排队，故尚未登记完整页面门禁通过；单设备结果只作为实机补充，不替代主题/语言/断点矩阵和截图审阅。
- 当前实机检查用于继续 PM 可用性审阅，不关闭性能测试运行态、空历史/回滚恢复、高级折叠数据、Rill 反馈详情及多主题多视口的专项验收。阶段 3 Goal 仍为 active。

### PM 当前 OpenWrt 配置状态审计补充（2026-11-18）

- 按用户建议，再使用当前运行的 OpenWrt PM 做了只读回查。Aurora Dark 中文桌面概况显示“系统配置方案：需要处理”，而“健康保护：已通过”。设备 overview.js SHA-256 与候选 `a31feb46d369356709d4bab93839901a0f0a8090` 相符，排除页面来自不同源码版本的可能。
- 设备 `ubus call performance-manager status` 显示核心服务运行、健康保护通过、没有缺少必需包；缺少推荐包 `tc-tiny`、`ss`、`nstat`、`kmod-sched-core`，对应 `tc`、`ss`、`nstat` 工具不可用。故原状态有真实依据，但概况没有告知原因，阅读上容易与健康保护通过混淆。
- 已在 PM 概况加入“未完整配置”状态及推荐测试／诊断工具缺失说明，并覆盖必需组件、能力不可用与可选组件降级提示。仅使用主题继承的原生颜色与表面，CSS 仅控制注释排版并更新缓存键。未安装缺失工具或改写设备配置。
- 定向检查通过：契约测试 31 项、profile 测试 3 项、英文／中文 PO `msgfmt --check`、`git diff --check`。修复提交 `97719ddf64f39583dbcc5107559b5dacf2318e35` 的 CI `44190049996` 与 LuCI SDK 构建 `44190050027` 均通过；x86_64 All-in-One 精确候选来自 run `44190049945`，APK SHA-256 `ac0fcf6aad76259e8d98dfb63d631d96e6b921291034d14006a09ccef9f0ca32`，已安装本地 OpenWrt。实机中文现显示“未完整配置／部分推荐的测试和诊断工具尚未安装”，健康保护继续显示“已通过”；PM/LuCI 配置哈希未变，未安装推荐工具或触发性能管理操作。双语 Real LuCI UI Gate `44190050000` 和多架构构建仍待完成，完整矩阵截图尚未审阅。详见 PM 仓库 `luci-four-repo-ui-evidence-2026-11-15/pm-overview-profile-status-followup-2026-11-18.md`。
- 精确 UI 矩阵 `44190050000` 英文捕获 1,968 行后报告 1,722 PASS、246 FAIL；所有 FAIL 均来自 Rill 页截图门禁要求固定两张表，而默认折叠态的反馈表按设计尚未挂载。移动 Aurora Dark 截图确认单表使用移动行标签、概况截图确认新增说明可读；没有其它失败类别。此为测试断言陈旧，不是页面样式缺陷。提交 `af4f5551c11059ebf092020715016af1b0d2ab3d` 修正为接受默认一张或反馈已挂载时两张原生表，触发新的完整 Gate `44195204145`；该运行通过及手动审阅仍待完成。保留首次报告和选定截图于 PM 仓库 `luci-four-repo-ui-evidence-2026-11-15/pm-profile-status-gate-review-44190050000-en/`。
- 同轮再展开本地设备 Rill 反馈后发现数据请求长期停留加载态。`history(50)` 返回包含完整持久事务的通用历史，设备上单条结果约 784 KB、10 条查询超时；并且 UI 从 `history` 而非实际写入 Rill outcome 的 runtime history 筛选。新增只读、限量、字段白名单的 `rill_feedback` RPC。设备审计还确认历史页“锁和事件记录”折叠区调用同一个大响应 `history(100)`；同时新增限 50 条、仅返回白名单元数据的 `history_summary` RPC，并更新两页 UI、rpcd read ACL、中英文文案。提交 `5df2302833f2d93887a9209eaaf79bdf37f136a2` 的 CI `44197512303`、UI SDK 构建 `44197512540`、多架构 All-in-One 构建 `44197512363` 均成功；精确 x86_64 APK SHA-256 `75d7a851101a569b3c192bd2c49bd5f2b1b86a02e3a226372fbd27d301f7953c` 已安装本地 OpenWrt。设备 API 读回：Rill 空反馈结果 38 字节，50 条历史摘要 23,380 字节；代码、配置与共享 Rill runtime 哈希核对通过。双语 Real LuCI 门禁 `44197512361` 英文与中文均完成 1,968/1,968 PASS、零错误。人工复核六主题的双语联系表，覆盖 8 页和窄屏、短屏横屏、平板、桌面代表断点；并复核 Rill/History 全宽度截图，未发现 PM 自定义样式导致的溢出、裁切、主题对比异常或断点布局问题。实机在 Aurora Dark 中文下展开反馈与历史摘要，空反馈状态与限量摘要均正常显示。详见 PM 仓库 `luci-four-repo-ui-evidence-2026-11-15/pm-overview-profile-status-followup-2026-11-18.md`。阶段 3 仍需完成其他仓库和剩余交互／运行态验收。

### PM 当前设备补充复核与 Nginx 交互发现（2026-11-18）

- 用户建议将当前运行的 OpenWrt PM 纳入审计。本轮重新登录 `192.168.2.1`，Aurora Dark 中文页面直接读取设备上的 PM：概况显示“未完整配置／部分推荐的测试和诊断工具尚未安装”，同时健康保护通过、服务运行、最近事务可读；与此前设备状态和 `overview.js` 候选哈希记录一致，未改设备配置或执行操作。
- Rill 页第一次展开“近期反馈”显示 XHR 超时；收起后重新展开后正常读到“暂时没有已验证的反馈”，排名和当前决策也正常。判定为一次性请求超时，尚未复现成代码缺陷；不据此改设备或改 PM 源码。页面手动复核沿用既有六主题／断点门禁截图记录，未另造覆盖结果。
- Nginx 隔离 OpenWrt 24.10.8 的证书表单检查发现 DNS-01 未选提供商时仍渲染空的“DNS Credentials”行，选择提供商后动态字段标签又贴靠输入框。修复 `certificates.js` 的空行显隐与凭据行结构，新增主题继承 CSS 网格布局（窄屏单列），更新共享 CSS 缓存键。复核中 DNS provider 未选择时该行消失，选 Cloudflare 后字段标签、输入及说明清晰分组；没有提交 ACME 请求或输入任何真实凭据。此前已用临时自签证书确认创建后显示有效，并在同一隔离容器中删除清理。
- Nginx 真实新增站点流程此前也复现显示名称允许 `-`/`.` 但 UCI ID 不允许的创建失败。当前工作树将显示名称规范化为内部 ID、前后端增加创建／编辑模式和冲突防护；隔离设备上已成功新增、编辑、拒绝规范化 ID 冲突，并删除测试站点。夹具的空格名称同步改为合法 ID，避免生成器在配置路径中使用空格导致无关的 `nginx -t` 失败。
- 当前 Nginx 改动尚未提交。JS 语法、RPC shell 语法、中文 PO、`git diff --check` 通过。后续仍需检查完整差异、双语全视图门禁和截图、构建候选包并校验安装；不得将本轮证书弹窗视图当作所有断点／主题验收通过。
- UPnP 中文真实 LuCI 门禁 `44174806960` 的 job `134468126758` 最近仍处于依赖安装步骤，英文 job `134468129637` 成功；需继续监控其最终状态，再决定是否重跑或修复运行环境。

### UPnP 向导模式切换实机复核与状态门禁补充（2026-11-19）

- 当前 exact-source Real LuCI Gate run `44250948304` 绑定 `0f57513243f7d341d46c82c5fe955a1cae1e2928`，英／中各 1,686/1,686 PASS、零自动化错误；artifact ID `14404359256`（EN，SHA-256 `b20eb36387af7333264b73e9e30b39849404a9eaa0ab28964870dab01baac2eb`）与 `14406415944`（ZH，SHA-256 `bdf63ab39a596e4d8db3e9d9eb153c5e6be491e93985e072973c2a88ccc9bf0f`）。逐主题宽度/短视口联系表和原图已人工审阅向导页：33 个 CSS 宽度×六主题×双语，另含 320×568 与 568×320；模式选择、步骤条和下一步操作布局清楚，无插件自有裁切、重叠或横向溢出。
- 在当前 OpenWrt 25.12.5 实机点选“自动模式”时，曾观察到选中态仍停在安全模式。追因到设备虽自报包版本 `1.3.16-r14`，实际提供的 `wizard.js` 却是旧实现，SHA-256 `88bd93f6c43bc6f75ba3e391a37b625c053c9246a56637db8e27c64c301d5f14`；这不是当前候选 source。已先备份原插件文件和配置，再从 Actions Build and Release run `44251020329` 安装 APK artifact `14403958134`（Actions archive digest `506ad8ab952feb56c355244bba6fb95a1af49d3d07529ed9615ff58702bac7c7`），下载 APK SHA-256 `bd996510d1ae94fb732a0706e50683617df325e6d5100debd4f4c6863da9b8c4`。
- 安装后设备服务保持启用／运行，UPnP UCI SHA-256 `b8cd1e7590b3f67e93e0eca8a707f64b8d9920957d7366c31545c0e0af65378a`、LuCI UCI SHA-256 `82a92faf05f9bde20eb6a60dba227046e80b2de59408845d8a812ef05d7ba23e` 未变，`uci changes upnp_nat_relay` 为空。设备实际 `wizard.js` SHA 改为 `e4bf6206022fafac8c506e16ea43dab0288f060a16f6fe7ee73e58713c3b5db6`，与 exact source 一致；实机中安全/自动按钮 ARIA selected state 由 `1/0` 切换到 `0/1`，再恢复 `1/0`，没有推进步骤或保存配置。备份、精确 APK、报告和 444 张向导原图、24 张联系表及 420 行人工审阅台账归档于 UPnP 仓库 `real-luci-ui-evidence-2026-11-15/upnp-candidate-0f575-install/` 与 `real-luci-ui-evidence-2026-11-15/upnp-run-44250948304-wizard-review/`；SHA256SUMS 核验通过。
- 为覆盖此前未纳入 screenshots 的交互模式状态，新增 `tests/real-luci-ui-wizard-mode.cjs` 和 workflow 步骤，点击安全/自动模式并断言 `aria-pressed` 与 LuCI 原生 `cbi-button-apply` 互斥；覆盖六主题、35 个视口和双语，不会前进向导或提交。`node --check`、`actionlint`、`git diff --check` 通过。仅测试工具提交 `a065bce0d7c9db2623c067e7a8abae0bade69da4` 已推送；Real LuCI Gate run `44379124801` 正运行，英／中两个 job 已进入依赖安装阶段，必须等新交互截图矩阵通过并人工审阅后才关闭这个向导状态项。
- UPnP 仍有其他未覆盖流程：向导各步／最终配置及真实服务状态、更改前后回退、填充映射表、长日志、依赖分支。此次结果只关闭精确候选默认向导和模式选择态审阅，不等同于关闭 UPnP 仓库或阶段 3。

#### Nginx 修复 Actions 跟进（2026-11-18）

- 上述站点创建与证书凭据布局修复已提交并推送至 `codex/luci-ui-audit-20261115`：`b028d67`（Fix Nginx site creation and credential layouts）。本地隔离 OpenWrt 实机交互检查通过；尚未在主路由器安装 Nginx 候选包。
- Real LuCI UI Gate 手动英文运行 `44209188167`（job `134482878456`）与 SDK PR Build `44209203157` 已启动，记录时 UI job 正安装 LuCI/Nginx 依赖，build 正初始化容器。workflow_dispatch 中文 UI 门禁需等待英文运行结束后启动，以遵守 workflow 的同分支互斥组；候选包产物和 SHA、双语截图人工审阅、设备安装均待完成。

### UPnP 门禁安装步骤超时诊断（2026-11-18）

- 中文 job `134468126758` 自 00:05 UTC 起超过 33 分钟仍停在前台 Docker `opkg` 安装步骤，尽管 shell 包装有 5/10 分钟 timeout；GitHub 日志接口只在 run 结束后开放。基于该可验证行为，更新工作流为在隔离 OpenWrt 容器内后台执行 opkg、用 runner 端有界轮询状态文件、取回容器日志并在更新重试前结束遗留的 opkg 进程。英文 UI job `134468129637` 已成功。
- 工作流修复提交 `474c0249444eaf1794ac748fd399c7d597c306b0` 已推送至 `fix/footer-full-version`。新 push 门禁 `44209713440` 已创建，记录时排队；旧卡住 run `44174806960` 暂仍显示运行中，需确认同分支并发取消和新 job 是否进入安装步骤，再检查英／中文截图与结果。
- 旧 job 在强制取消请求后仍占用原分支队列；为保证修复版可验收，已在相同 SHA 创建临时隔离分支 `codex/upnp-gate-bounded-20261118`，并手动启动双语 UI Gate `44210389705`。该分支只用于此轮工作流验收，完成后清理。Nginx 英文矩阵 `44209188167` 与 APK/IPK 构建 `44209203157` 仍在运行。

### PM 当前设备视觉复审与间距修正（2026-11-18）

- 将 UI/UX Pro Max 用于 PM 页面评审，查询到的适用指导强调信息不能只靠颜色、标题层级顺序正确、表单有可见标签且错误／提交状态应明确；这些为审查参考，最终仍以 LuCI 主题原生组件及实机截图为准。
- 在运行 OpenWrt 的 Aurora Dark 中文 Rill 页面直接复核：排名卡的“刷新 Rill 决策”按钮几乎贴着表格；“排名／近期反馈”双卡后紧接“高级详情”卡，纵向留白约 4px，明显压缩信息分组。该项是插件自有布局问题，不是主题外观问题。
- PM 已提交并推送精确候选 `056d2b3de2a362b9235de77e6a437c7902e2df4c`：为 Rill 动作区和表格增加主题变量驱动的分隔留白，并在网格卡片后增加一致的区块间距，同时更新 CSS cache key。只暂存了三个源文件；PM 工作树中原有 `tests/real-luci-ui-visual.cjs` 及证据目录仍保留未提交／未暂存。
- 精确 SHA 的 CI、LuCI SDK 包构建、多架构包构建和 Real LuCI UI Gate 已由 push 启动，runs 分别为 `44210877397`、`44210877294`、`44210877454`、`44210877486`；待完成双语截图矩阵人工审阅、候选包 SHA 核对、设备安装后复看 8 页及主题／断点情况。
- Actions 跟进：PM CI `44210877397` 全部成功。Nginx 25.12 APK job 已成功，24.10 IPK、Real UI Gate `44209188167` 仍运行。UPnP 旧卡住 run `44174806960` 终于结束为 cancelled；修复工作流的原分支 push run `44209713440` 已通过有界依赖安装并进入 Playwright 初始化。隔离分支上相同 SHA 的重复全矩阵 run `44210389705` 已请求取消，留下 `44209713440` 作为正式修复验证。
- Nginx 构建 run `44209203157` 已整体成功。25.12 APK `luci-app-nginx-manager-1.8.11-r22.apk` SHA-256 `4ceb82695bdfefd365e41aca0cfaa28d3d7334501350b7d0a52404c6774687b8`；24.10 IPK `luci-app-nginx-manager_1.8.11-r22_all.ipk` SHA-256 `954571cb003e47918717167ba7e18574bbf0ab95b3281133e14c7d90b6977262`。APK 已安装至设备 OpenWrt 25.12.5。安装前后 `/etc/config/nginx_manager` SHA-256 均为 `fc877cd43100e4718cdd9cf68f5eb85a04194e8fa9d30b8ab1dddb6164a90cbe`，`/etc/config/nginx` 均为 `c562c024a1fb7ee6f6e99bc11492fa5b08ce311dac38c30a80f2da32e0e29d8c`，Nginx 服务保持运行。设备已加载证书页 JS、站点页 JS 和主题 CSS 与候选 `b028d67` 匹配；Edge/IAB 登录后确认设备证书列表页完整载入并显示有效状态。没有打开含真实凭据的编辑表单。
- Nginx 构建 run `44209203157` 已整体成功。25.12 APK `luci-app-nginx-manager-1.8.11-r22.apk` SHA-256 `4ceb82695bdfefd365e41aca0cfaa28d3d7334501350b7d0a52404c6774687b8`；24.10 IPK `luci-app-nginx-manager_1.8.11-r22_all.ipk` SHA-256 `954571cb003e47918717167ba7e18574bbf0ab95b3281133e14c7d90b6977262`。APK 已安装至设备 OpenWrt 25.12.5。安装前后 `/etc/config/nginx_manager` SHA-256 均为 `fc877cd43100e4718cdd9cf68f5eb85a04194e8fa9d30b8ab1dddb6164a90cbe`，`/etc/config/nginx` 均为 `c562c024a1fb7ee6f6e99bc11492fa5b08ce311dac38c30a80f2da32e0e29d8c`，Nginx 服务保持运行。设备已加载证书页 JS、站点页 JS 和主题 CSS 与候选 `b028d67` 匹配；Edge/IAB 登录后确认设备证书列表页完整载入并显示有效状态。没有打开含真实凭据的编辑表单。
- Nginx 英文 UI Gate run `44209188167` 已通过 exact commit `b028d67` 的 1,734/1,734 行矩阵，零 errors，涵盖 9 个视图、34 个宽度／短视口和六种主题模式。自动 gap 检查在 216 个相关记录中，overview top/bottom 留白最小 16/12px、控制组 24px；备份按钮／保留数最小间距 20px，日志控件最小 16px，均无小于 8px 的记录。人工打开复核六主题 320px Sites、Aurora Dark 多视图与 1319px Bootstrap overview/Backups，未发现裁切、溢出、粘连或主题表面不协调。报告明确尚不覆盖手动交互、成功证书／完整恢复流程及设备行为；这些继续单独验收。artifact SHA-256 `8b34dd03479166000d0e52cc43ebffcc3cf32d0d48c1c1f954b6cb6b9a34fd8f`，截图和报告位于临时目录 `/tmp/nginx-ui-artifacts-44209188167/visual/en/`。中文 Gate `44212587421` 已启动。
- 安装后 Nginx 设备站点页和“添加站点”对话框可正常打开；对话框字段说明和三种模式选择可见，关闭时点“取消”，没有在主路由写入站点。已运行的站点数据不在截图证据中保存或再次复制。新增／编辑／规范化 ID 冲突与备份恢复流程此前已在隔离 OpenWrt 测过，仍需对照 exact b028d67 的远端门禁及报告确认覆盖。
- CFI 当前设备 `settings` 页另行复核：表单分组与字段帮助正常，但 Aurora Light 固定浮动工具条在窄屏滚到底部时压住 LuCI 原生 `cbi-page-actions`。追踪确认 CFI 自有 CSS 只控制插件卡片／动作／页脚，不设置或移动 `cbi-page-actions`；同一 b0455209 的六主题 UI Gate Bootstrap 截图没有 Aurora 的浮动工具条，因此归类为主题工具条与 LuCI 原生保存栏的叠放，不改 CFI CSS 给主题问题擦屁股。需在 CFI 互动验收中继续核对其他插件自有布局是否触发相同避让问题。中文 Gate 报告 `44123328312` 有 1,374 PASS、456 条带依据 N/A、零 errors，覆盖六主题与 8 个页面。该提交的 `tests/real-luci-ui.cjs` 交互 artifact 同时有 4 项 PASS（来源刷新保留草稿、LuCI 清日志模态取消、减少动态效果、来源 RPC 错误状态）；未覆盖的设置保存／校验、来源增删、Rill 可用态和插件实际 OpenClash／PassWall 表单仍需补验。
- 当前 OpenWrt Aurora Light 上只读复核了 CFI Settings、Sources、Intelligence 和 Logs 四页：表单字段分组可读，来源空态／状态表和日志筛选／输出均未见插件自有溢出或按钮粘连；Rill 诊断状态按当前设备配置显示 disabled/native ranking，没有修改配置或触发测速／保存。设置页全页底部叠放在 Bootstrap 同提交截图中不出现，进一步支持其来自 Aurora 固定工具条与原生保存栏组合；截图数据属于设备实时视图，未复制真实日志或网络数据到仓库。
- PM `056d2b3` 英文 UI Gate 已完成并通过 1,968/1,968 行、零错误，覆盖全部八页、六主题和 41 个 CSS／短视口点；英文 artifact SHA-256 `ff44a1b876469f11ed04e474f8463f2aa90a9b3790cd0614d372bd284320a6da`，报告和截图位于 `/tmp/pm-ui-artifacts-44210877486/visual/en/`。人工复核 Rill 页六主题下的 320px 截图、Aurora Dark 与 Bootstrap Light 1320px，以及短屏横向视图：按钮和表格分隔、网格与高级详情卡片间距清楚，无裁切或横向溢出；中文 Gate 仍运行，安装 PM 精确 APK 和当前设备复看尚待完成。报告不覆盖 populated/error/interactions 与本机安装，不能提前视为这些场景 PASS。
- 同一英文 artifact 下逐页查看 PM 八个 Aurora Dark 320px 页面，概况状态块、优化卡片、测试字段与主操作、能力列表、历史空态、高级诊断折叠和设置表单均完整可读，未发现可复现的插件布局问题；设置的底部原生保存栏保持可用。宽屏、其他主题和有数据／错误／展开状态仍按矩阵和实际交互继续审。
- **PM 精确包安装后实机复核（2026-11-18）**：用户建议将当前 OpenWrt 上运行的 PM 也用于审计；已在已安装 `056d2b3de2a362b9235de77e6a437c7902e2df4c` 候选后检查 Aurora Dark 中文 Rill 页面。AX 页面明确显示“RILL 运行时可用”、服务与决策内容已载入；320px 窄视口截图确认刷新按钮与排名表之间有可见留白，排名表与“近期反馈”及“高级详情”分组不再紧贴，底部页脚完整可达。页面只读复核，未触发刷新、配置保存或服务操作。PM 配置哈希保持 `19bf0cd88577fca49e0902633d0fc8a38beb480ae1297d00433b888c1da1a505`，共用 Rill binary 哈希保持 `c3ad43ed73cc7b57dbc3835ea01f8b6ff03d69ab213655b72c60e25f05f96abe`，服务仍运行；候选 CSS 与 `rill.js` 的设备文件 SHA 与 commit 一致。UI Gate 中文和 Nginx/UPnP 中文矩阵在记录时仍运行。
- **UPnP 英文全矩阵及截图人工复核（2026-11-18）**：精确源码 `474c0249444eaf1794ac748fd399c7d597c306b0` 的 run `44209713440` 英文 artifact 已通过 1,686/1,686、零错误，覆盖 8 个注册页面／root alias、6 种主题、33 个 CSS／断点邻值宽度及短屏竖／横向视口；所有截图页均确认主题、插件 CSS 和 PM 对齐页脚已加载，无横向溢出。人工复看了 Aurora Dark 320px 全部 8 页以及六主题 320px 概况页；未见裁切、重叠或按钮粘连，长表单／诊断页可通过纵向滚动访问。概况统计卡在 Aurora Light 768px 截图中布局均匀；自动记录的统计区相邻留白差最大 23px，视觉间距仍在合理范围。报告明确不覆盖手动向导状态流转、真实服务／网络变更、填充后的映射与长日志；这些需独立验证。英文 artifact 路径 `/tmp/upnp-ui-artifacts-44209713440/real-luci-ui-evidence-en-run-44209713440-attempt-1/visual/en/`，中文矩阵仍运行。
- **PM `056d2b3` 双语 UI Gate 与实装后复核收尾（2026-11-18）**：中文 run `44210877486` 现已完成，通过 1,968/1,968、零错误；六主题、八页、41 个宽度／短屏点均覆盖。中文 artifact SHA-256 `bb1a6d53cc9a96a773180e4e46d1d4d3c77674ee903de96eda1209f8a6505c69`。人工复核中文 Aurora Dark 全部八页窄屏、Rill 六主题 320px 截图；概况状态说明、设置表单、历史／高级折叠以及 Rill 排名／反馈分组可读，未见插件自有裁切、横向溢出或主题色冲突。PM 英文 gate SHA 另见前项。自动报告的未覆盖项为业务交互、有数据／错误状态和已安装路由；实装后 Rill 页检查已补充，但其他页面实机互动和额外状态仍继续。
- 实机 Rill 页追加了只读展开态检查：近期反馈加载后显示清晰空状态；高级详情展开的 JSON 在 320px 视口中换行，未产生横向溢出，卡片与排名／反馈区间距明确。未记录设备拓扑内容，也未修改 PM 配置或调用运行操作。
- 中文 PM 320px Aurora Dark 概况截图还发现 Rill 未部署时状态徽标把最后一个“署”字单独折到下一行。初版 `d58f527` 因破坏 CI 规定的英文 msgstr=msgid 目录一致性而使静态 CI 失败（SDK 包构建通过）；未安装该候选。改用概况专用短标签 `Not provisioned`／`未部署`，Rill 详情仍保留完整状态翻译，并在 `luci_render_smoke.js` 增加短标签／完整标签并存断言。修正提交 `8f46cc45…` 已推送；同 SHA 双语全矩阵、CI、SDK 和多架构构建等待完成。
- **Nginx/UPnP 中文截图矩阵收尾（2026-11-18）**：Nginx `b028d67a926260b0a54d381791bb6067e1e23843` 中文 run `44212587421` 通过 1,734/1,734、零错误；9 个视图、6 主题、36 个宽度／短屏点。artifact SHA-256 `199ef52f6b3e6416c89306ae961ed553dc3eedebb03c77cec8616a7e2061453f`。相关间距检查：overview controls 最小 24px、备份 controls 20px、日志 controls 16px，均无贴靠；六主题概况与 Aurora Dark 320px 所有主页面截图均复核，无插件样式裁切／横溢；Aurora Light 768px 概况大块和状态卡视觉留白协调。报告仍未覆盖业务交互、成功证书/ACME、完整备份恢复及装机后的互动。
- UPnP `474c0249444eaf1794ac748fd399c7d597c306b0` 中文 run `44209713440` 通过 1,686/1,686、零错误；8 个实际页面加 root alias、6 主题、35 个宽度／短屏点。artifact SHA-256 `58e89cc7dec5bb305c3839ca6bc99cffbb5e703f797cbfa73d8a80e3b89e39d8`。人工检查了中文 Aurora Dark 全部 8 页、六主题概况以及长向导／设置／OpenClash／诊断页面；未见插件自有裁切、重叠或横向溢出，滚动可达。业务向导状态流转、真实网络/服务更改和填充的映射/长日志仍列为门禁未覆盖项。
- **UPnP 设备向导安全路径（2026-11-18）**：在当前 OpenWrt 的中文 320px 视口以安全模式完成 10 步向导的前端流转，检查了网关检测、UPnP 发现、WAN/端口/OpenClash 表单和最后摘要；按钮和字段可读，摘要表纵向滚动可达。最终停在“保存配置”按钮前并返回 PM 页面；没有切到自动模式，没有按保存，没有应用向导的任何 UCI／服务更改。步骤 4/5 只读取现有网络状态及 UPnP 发现结果。精确页面版本仍为设备已安装的 UPnP r14；最新 `474c024` 是仅工作流修复提交，UI 源码与已装候选相同。
- `8f46cc4` 的静态 CI 与 LuCI UI SDK 包构建均通过；x86_64 All-in-One APK SHA-256 `8f80457bb77a47050f6b54d49301d6f9b689df75833fd9c7a2514fd0bea37c94` 已安装。安装前后 PM UCI SHA-256 均为 `19bf0cd88577fca49e0902633d0fc8a38beb480ae1297d00433b888c1da1a505`，共享 `/usr/bin/rill-runtime` SHA-256 均为 `c3ad43ed73cc7b57dbc3835ea01f8b6ff03d69ab213655b72c60e25f05f96abe`；设备 zh-cn LMO 与该包 manifest 对应 SHA-256 `0e21d42698755268beb0bbe32582d1bdb7c76e13d2da8864a0d05e9da8fc731a`，PM 运行且 Rill available/compatible。设备脚本 SHA 与 `8f46cc4` 完全一致。
- 该实机概况复核确认 PM 首块仅有 3 个状态小卡，与 Nginx/UPnP/CFI 的 4 项不齐；分类为 PM 自有信息层级／数量问题。提交 `07f03a90…` 将 Rill runtime 短状态作为第 4 个卡片，并从下方系统信息表移除重复行。中文／英文渲染 smoke、PO 检查通过；新的精确 SHA 全套 UI/CI/SDK/多架构 Actions 等待中，07f03a9 尚未部署或验收。
- **PM 四状态卡实机验证（2026-11-18）**：`07f03a9` 精确 x86_64 All-in-One APK SHA-256 `a791bf192a23a911dc4795c5ccef396cdfaee244fc15bd9462a6736d4e2c246e` 已安装 OpenWrt。PM 配置 SHA 保持 `19bf0cd…`，Rill binary SHA 保持 `c3ad43ed…`，服务及 health guard 正常，Rill available/compatible，中文目录与脚本文件 SHA 同源一致。设备 320px Aurora 页面已实拍并由 AX 树确认“系统配置方案／健康保护／自动化模式／Rill 运行时”四卡显示，Rill 行从系统信息表移除，避免重复；短状态“可用”清楚。该截图同时出现 Aurora 浮动工具条盖住卡片右边框的情况，按钮不遮盖文字；这是主题固定工具条覆盖内容区，属于主题自身问题，不做插件 CSS 避让。07f03a9 全部 CI、SDK、multi-arch 与精确主题断点截图人工复核尚未结束。
- **继续使用当前 OpenWrt PM 做只读审计（2026-11-18）**：按用户建议，再检查设备已安装的精确 `07f03a9` PM Rill 页面及展开的高级详情。页面显示运行时可用、建议保持当前配置、冷启动样本不足和空反馈状态；展开详情后 JSON 内容仍在页面卡片中可读。没有触发刷新、回滚、基准测试、配置保存或服务控制，也未把设备拓扑数据记入证据。该真实运行状态补充了矩阵静态首屏无法覆盖的 Rill 可用／冷启动／反馈空态；PM 矩阵与最终多架构构建仍等待完成。
- **PM `07f03a9` 多架构构建收尾（2026-11-18）**：Actions run `44219585109` 已整体成功，x86_64、armsr/armv8 和 mediatek/filogic 三架构 All-in-One 构建均成功；Release assembly dry-run 与 final-release-evidence 两项也成功。下载的工件清单 `final-release-evidence.json` 将 `07f03a9029c494a8ee7c55c395a7c57eda4b2e36` 对应的构建证据链和 APK 精确验证判为 PASS。x86_64 APK SHA-256 与设备安装包相符：`a791bf192a23a911dc4795c5ccef396cdfaee244fc15bd9462a6736d4e2c246e`；manifest 确认 Runtime 未打包，由共享的 `rill-runtime-preview` 提供。三架构包与 Runtime ownership 工件位于 `/tmp/pm-build-artifacts-44219585109/`。登录恢复后再次在 OpenWrt Aurora Dark 桌面实时观察到四张概况状态卡和无重复 Rill 系统信息；浮动按钮覆盖右侧边框仍归 Aurora 主题层，不作为 PM CSS 缺陷。唯一未收尾的 PM 精确门禁为 run `44219585009`：英文矩阵捕获仍在运行，中文排队；其报告和全量截图需完成后继续复核。
- **PM `07f03a9` 英文矩阵和人工视觉复核（2026-11-18）**：英文 Real LuCI UI Gate run `44219585009` 的 en job 已成功。报告精确 SHA 为 `07f03a9029c494a8ee7c55c395a7c57eda4b2e36`，1,968/1,968 PASS、零门禁 errors、零 browser errors；覆盖 8 页、6 种主题、39 个断点宽度及两个短视口，1,968 张主截图与 96 张短视口截图均存在。artifact digest `sha256:12cc63df0f5415efd87e185de20f8285524711f017d3a302912650d3f377f009`，解包至 `/tmp/pm-ui-artifacts-44219585009-en/`。人工联系表核对了 Aurora Dark 320px 全部 8 页、全部 6 主题的 320px 全页面；概况四状态短文案在各主题均完整，Rill、设置、性能测试、能力、历史与高级页面均可纵向阅读，按钮／LuCI 保存栏和 footer 可达，未发现 PM 自有裁切、覆盖或页级横向溢出。报告的 `tabMenu.horizontalOverflow` 在四种 Bootstrap theme 下均记录 5px，但发生于 LuCI 生成的原生页面导航容器，整体视口无溢出、截图中菜单可见完整；PM CSS 不定义该导航，因此按主题／LuCI 原生层分类，不加 PM 避让样式。该 run 的 zh_cn job 正在执行同一矩阵；中文完成后仍需下载并人工复核。
- **PM 当前设备其余七页实机复核（2026-11-18）**：对精确 `07f03a9` 设备包再次检查智能优化、性能测试、能力、Rill 智能、历史与回滚、高级、设置（概况在上一项已复看），均可加载并呈现当时真实数据；导航切换时会短暂出现“正在载入视图”，之后正常渲染。桌面 Aurora Dark 下性能测试动作／路径／测量类型和“开始测试”按预期成组，能力及高级卡片对齐，Rill建议、历史事务和折叠技术详情可读。历史真实事务页显示回滚按钮，本轮没有点击；未启动基准测试、保存或重置设置。设置页到达底部后 Rill 运行时表单、Footer 和保存／重置操作均可见；Aurora 的固定浮动工具栏与 LuCI 原生底部操作栏在右边缘相交，可能遮住 Reset 按钮边缘。源 CSS 未控制 `.cbi-page-actions` 或 Aurora 工具栏，归类为主题与 LuCI 原生操作栏碰撞，不在 PM 中增加主题补丁。PM 页面／服务／配置保持只读。
- **PM `07f03a9` 中文矩阵和视觉复核（2026-11-18）**：同一 Real LuCI UI Gate run `44219585009` 的 zh_cn job 已成功；报告 SHA 与 `07f03a9029c494a8ee7c55c395a7c57eda4b2e36` 一致，1,968/1,968 PASS、零门禁及浏览器错误，8 页、6 主题、39 个宽度加两个短视口。1,968 张页面截图和 96 张短视口截图逐行核验均存在。artifact digest `sha256:81ca15b95823a0735761b26ef40b6db7fd0362671384f47ead9e03eccdc0a00f`，按 artifact ID `14391669277` 下载，报告／截图位于 `/tmp/pm-ui-artifacts-44219585009-zh/`。人工检查中文 Aurora Dark 320px 八页、六主题 320px 八页；并以各主题 39 个宽度的概况联系表复看四状态卡从单列、三列到四列的断点转换。四卡标签不被拆字或遮挡；内容顺序和系统信息无重复项。其余各页和所有视口矩阵的自动截图完整，报告页级溢出为 0。中文与英文 PM UI gate 的截图／报告均绑定 exact `07f03a9`；本项通过只关闭该提交的主题／语言／断点截图门禁。业务交互及填充／错误状态仍是报告明确未覆盖范围，需在整体 PM/四仓 Goal 继续收尾。
- **PM 当前 OpenWrt 有数据历史页复核（2026-11-18）**：实机打开“历史与回滚”页，验证现存事务的已提交状态、对象信息、回滚入口及事务详情折叠都能一起显示；主卡和下方高级历史详情分组边界清楚，桌面视口下没有插件造成的裁切或横向溢出。没有点回滚或展开可能含设备细节的日志；不复制现有事务内容。复核后已回到概况页。该项补足了构建矩阵空历史态以外的一种真实填充态；窄屏填充态及可展开详情仍应通过隔离夹具补齐。
- **按用户建议将当前运行中的 OpenWrt PM 纳入本轮复核（2026-11-18）**：重新查看已安装 PM 的实机概况页，确认真实运行状态、配置摘要、保护状态和最近事务均可读，信息没有重复或裁切。实机数据只用于视觉和只读状态核对，不复制设备专属值；不进行保存、重置、回滚或测试操作。Aurora 右侧浮动工具栏与视口边缘的关系继续归主题／LuCI 原生层，插件不添加主题修补。连同此前实机七个子页面、有数据历史和安全健康检查，当前 OpenWrt 作为真实填充态证据纳入 PM 验收；需要产生副作用的状态仍在隔离 OpenWrt 验证。
- **PM `07f03a9` 隔离 OpenWrt 补充交互态矩阵（2026-11-18，英文 PASS）**：在独立 OpenWrt 24.10.8/Aurora 环境，对 8 个 PM 页面、6 种 LuCI 主题、39 个视口宽度（含断点邻值）、2 个短视口，以及 benchmark 的 health-only 与 passive-before/after 两种只读观察态运行同一 Playwright Gate。报告绑定源 SHA `07f03a9029c494a8ee7c55c395a7c57eda4b2e36`，2,460/2,460 PASS、0 errors；总 PNG 2,580 张。已人工查看 Aurora Dark 320px 概况、health-only 与 passive-before/after 全页截图：移动端状态卡自然堆叠，测试控件和结果步骤无裁切；健康快照说明不是性能结果，被动观测说明未更改设置。报告 `/tmp/pm-live-audit-20261118/en/report.json`，截图 `/tmp/pm-live-audit-20261118/en/`。门禁脚本 SHA-256 `0daed2cce6065ec428780852dcb0c6627ee6e96e6b41011160c789ac923f1bca`；脚本为既有用户未提交修改，本轮只运行、未编辑。报告的 `notCovered` 明确保留人工审阅、受控 A/B 生命周期、其它业务变更与已安装路由器行为，不将这些自动矩阵结果夸大为全验收。
- **PM `07f03a9` 隔离 OpenWrt 补充交互态矩阵（2026-11-18，中文 PASS）**：与英文使用同一独立 OpenWrt 24.10.8/Aurora、同一报告脚本及来源 SHA；8 页、6 主题、39 视口宽度、2 短视口、health-only 与 passive-before/after 两状态，共 2,460/2,460 PASS、0 errors，2,580 张 PNG。报告 SHA `07f03a9029c494a8ee7c55c395a7c57eda4b2e36`，报告 SHA-256 `697205aaee1960c5a513e0b582ab28aa46f0a1dd6c2dbc710b9b81b77c47ef29`，文件 `/tmp/pm-live-audit-20261118/zh/report.json`，截图 `/tmp/pm-live-audit-20261118/zh/`。人工复看 Aurora Dark 320px 中文概况、健康检查、被动前后观测截图：状态卡上下堆叠清楚，表单选择器留白充足，状态说明在卡内完整可读，footer 可到达；观察完成态分别明确写出“不是性能测试结果”及“没有修改任何设置”。英文／中文这两轮仅关闭补充视觉/断点/只读观察门禁，报告所列受控 A/B 生命周期、其它业务变更与已安装路由器仍在后续清单中。
- **PM 受控 A/B 真交互复核与修复（2026-11-18）**：在一次性隔离 OpenWrt 24.10.8 中用 `network.buffers`／本机端点跑真实配套 `iperf3 3.22` control 与 candidate。候选值 `rmem_max` 从 `7500000` 临时升至 `15000000`，受控候选验证后精确恢复 `7500000`；健康检查通过、会话 `completed/validated=true/rolledBack=true`、事务锁已清空。第一次页面未能显示结果：日志定位为 `smart_record_validated_outcome()` 使用未声明的 `state`，写完已验证会话后抛出 ReferenceError，使页面把成功回滚误呈现为错误码 `9`。修复为复用 `smart_context_stats()` 返回的 `row.state`，新增回归断言；同时在 benchmark RPC 响应中省去仅供内部校验、体积很大的原始 nftables 快照（完整快照仍保留于后端会话文件）。修订后的后端在隔离设备跑出成功页面响应，Smart Decision 已记录 1 个样本；修复前后 sysctl 还原值均为 `7500000`，锁清空。当前源码另已将完成态进度项改为“回滚保护”并加入中英文结果摘要；其最终结果状态尚待精确候选 UI 在 disposable OpenWrt 上复核。定向 Python 测试 29 项通过，ucode 编译、JS 语法、PO `msgfmt --check`、`git diff --check` 通过。修复已提交 exact `06521c741ce9e9f6c5a9e558475fd79ebd81e62e`（`06521c7`）；原 CI `44238351616`、LuCI SDK 构建 `44238351665` 和多架构构建 `44238351676` 均成功，原双语 UI run `44238351612` 因中文 runner 依赖安装卡住被取消。workflow-only 提交 `1aab592c69b7cfcf5e9fbf83f4f06013a3c5cb4d` 修复有界重试；CI `44242883338`、三架构构建 `44242883316` 和中文 UI Gate `44243528118` 均成功，英文 1,968/1,968 证据保留自原 run。`44242883316` x86_64 APK 与主路由已安装候选 SHA 均为 `31889d65241a61df630c20dd8a07253506d48c1d0fb30721b6c310ead69ea2fb`，manifest 确认 Core 与源码匹配。仅 workflow 在 `1aab592` 发生变化，因此 UI 源码仍绑定 `06521c7`。主路由安装包哈希、组件哈希与配置状态已核验；不会在主路由执行 A/B、保存、回滚或性能测试。下一步需在 disposable OpenWrt 安装／加载精确完成态 UI 并完成人工视觉复核。
- **PM 受控 A/B 修复候选实机审计（2026-11-18，进行中）**：用户建议把当前运行中的 OpenWrt PM 纳入审计后，已在主路由 `192.168.2.1` 上通过 `apk --force-reinstall` 重装 exact `06521c7` x86_64 All-in-One APK（SHA-256 `31889d65241a61df630c20dd8a07253506d48c1d0fb30721b6c310ead69ea2fb`）。安装前模拟只涉及同包同版本替换；安装后 PM UCI/LuCI 配置哈希原样，`rmem_max=8388608`、服务 `running`、`rill-runtime-preview-1.5.6-r6` 和 `/usr/bin/rill-runtime` SHA-256 `c3ad43ed73cc7b57dbc3835ea01f8b6ff03d69ab213655b72c60e25f05f96abe` 均未变化。设备实际安装的 Core 脚本 SHA-256 `5b330bc7…`、Benchmark JS `9681279a…`、共享 UI CSS `4d50864e…` 和中文 LMO `c26a8579…` 均与 exact `06521c7` 构建证据相符。重新登录后在 Aurora Dark 中文真实设备检查了八页：概况、智能优化、性能测试、能力、Rill 智能、历史与回滚、高级、设置均能显示填充态内容；Rill 页面首屏需等待建议 RPC 完成（设备端 `recommendations` 约 3.5 秒），之后运行时、当前决策、排名和反馈入口均正常。历史页发现已有已提交事务和回滚按钮，仅检查展示、不按回滚；主路由未执行 A/B、保存、重置、刷新或配置更改。当前主题固定浮动工具栏盖住边缘卡片边框仍属 Aurora 自身表现，不做插件补偿。
- **PM `06521c7` 英文真实 LuCI 断点矩阵**：Actions Real LuCI UI Gate run `44238351612` 英文 job PASS，exact SHA `06521c741ce9e9f6c5a9e558475fd79ebd81e62e`。8 页、6 种主题、39 个响应宽度（含断点邻值）和 2 个短屏，共 1,968/1,968 PASS、0 errors；报告 SHA-256 `2d62772195cc4c766041eb134197d1b14f5b6c4e7b00327cbd25f61115861df4`，报告 `/tmp/pm-ui-06521c7-gate/visual/en/report.json`，全截图目录 `/tmp/pm-ui-06521c7-gate/visual/en/`。下载 ZIP 已展开 2,065 个文件（含报告和截图）。已人工查看六主题在 320、768、1280px 的八页联系表，确认主题亮暗配色、卡片堆叠／多列转换、设置表单、页脚和滚动结构均未见插件自有重叠、截断或内容裁切；设备实机 Aurora Dark 全八页另行复核。Gate 报告 `notCovered` 明确指出交互填充／错误状态、已安装路由器行为不在矩阵覆盖范围内。原 run 的中文 job 因 runner 长时间停在无步骤超时的 Playwright/Chrome 依赖安装而取消；英文截图报告继续作为 `06521c7` 页面源码证据。PM 代码未变，随后仅为依赖步骤加入限时重试的 workflow-only 提交 `1aab592c69b7cfcf5e9fbf83f4f06013a3c5cb4d`，其中新的中文-only dispatch `44243528118` 正在安装中文目录并准备重跑矩阵。
- **PM Real LuCI 门禁依赖超时修复**：旧 run `44238351612` 中文 job 在 `Install Playwright and locate Chrome` 超过 15 分钟无进度（此前成功 run 同步骤约 20 秒）。为避免无限等待，只修改 `.github/workflows/real-luci-ui.yml`：apt/npm 依赖命令加 3 分钟上限、两次重试，步骤总限时 25 分钟；`actionlint` 与 `git diff --check` 通过。提交 `1aab592` 只含此 workflow 文件；相对已安装 `06521c7` 没有任何 `package/` 源码差异。CI `44242883338` 与三架构构建 `44242883316` 已成功，中文-only Gate `44243528118` 也成功；英文 `06521c7` 原有 1,968 项 PASS 作为源码相同的英语证据保留。该英语 Gate 作业报告及 `1aab592` 中文截图矩阵的准确范围和已审阅结果见 PM UI 证据目录。

### 当前运行 OpenWrt：PM Vantage 主题对照（2026-11-18）

- 按用户建议，将当前运行中的 OpenWrt PM 加入审计。先记录 LuCI 主题偏好，再临时切到设备已安装的 Vantage，在同一组真实设备数据下检查 PM 概况、智能优化、性能测试、能力、Rill、历史与回滚、高级和设置八页。八页均成功载入；概况／能力卡片网格、智能优化说明区、性能测试表单、Rill 排名、历史事务卡、高级信息卡和设置表单均使用当前主题的原生视觉组件，没有因 Vantage 产生插件自有重叠、裁切或不可用控件。实机检查只观察内容，未启动性能测试、刷新 Rill、保存设置或执行回滚。
- 观察到 Aurora 与 Vantage 对同一插件内容的视觉密度不同：Vantage 卡片间隔更清晰，字段布局更紧凑；这来自主题原生外观，应继续由插件复用 LuCI 原生类和主题变量，不用 PM 私有硬编码覆盖主题。此次确认不是所有宽度的替代证据；断点覆盖仍由真实 LuCI Playwright 矩阵承担。
- 完成后恢复 `/luci-static/aurora` 并在浏览器确认 Aurora Dark 设置页已载入。设备只读核验：`/etc/config/luci` SHA-256 恢复为 `82a92faf05f9bde20eb6a60dba227046e80b2de59408845d8a812ef05d7ba23e`，PM 配置为 `19bf0cd88577fca49e0902633d0fc8a38beb480ae1297d00433b888c1da1a505`，Rill runtime 二进制为 `c3ad43ed73cc7b57dbc3835ea01f8b6ff03d69ab213655b72c60e25f05f96abe`，服务仍为 running，`rmem_max=8388608`。
- workflow-only 触发的多架构构建 `44242883316` 已通过，x86_64、armv8 和 MTK Filogic 全部成功。
- 中文断点矩阵 `44243528118` 已成功完成（exact workflow source `1aab592`，包/UI 源码仍为已安装的 `06521c7`）：8 页 × 6 主题 × 39 宽度 + 两种短视口，1,968/1,968 PASS、零错误。报告 SHA-256 `55c32c5036fe91817fef1b581950fc7ade1b22ce1b645a519c36b175fe5e6d8c`。已人工查看六主题在 320/768/1280px 的八页中文联系表，确认标签换行符合预期，无插件自有内容重叠、裁切、截断或卡片／表单断点破坏。证据包索引、报告与 18 张联系表：`luci-four-repo-ui-evidence-2026-11-15/pm-ui-06521c7-zh-run-44243528118/`；完整截图保存在 Actions artifact `real-luci-ui-evidence-run-44243528118-attempt-1`。除 Rill 页面填充数据外，本矩阵以默认运行态为主；错误态、业务交互状态与路由器装机行为依赖对应的专项/实机复核，不能由默认态截图替代。
- 按用户“每个断点、每个页面都需视觉检查”的门槛补充严格人工复核：从 1,968 个截图生成 48 张联系表（6 主题 × 8 页），每张包括全部 41 个视口（39 常规宽度含响应断点邻值 + 320×568 / 568×320 短屏）。逐张复核后，所有页面/主题/断点组合均未发现 PM 自有重叠、裁切、溢出或布局突变；320px 导航自然换行。该完整联系表保存在 `luci-four-repo-ui-evidence-2026-11-15/pm-ui-06521c7-zh-run-44243528118/all-viewports-by-route/`。该结论只针对矩阵实际覆盖的默认填充状态；交互后及错误/业务状态由各专项场景另行覆盖。

### Nginx `b028d67` 备份恢复交互闭环（2026-11-18）

- 在运行中的隔离 OpenWrt 24.10.8 x86/64 容器 `nginx-ui-goal-20261118` 验证；容器里 `backups.js`、`certificates.js`、RPC 脚本 SHA-256 与 `b028d67` 工作树逐项一致。未在日常路由上操作。
- 经 LuCI 页面创建备份 `2026-11-18-055912` 后，用页面 Disable 操作将仅供视觉测试的 `ui_gate_site_enabled` 从 enabled 改为 disabled。备份记录 enabled=1。再从 Backups 页面点 Restore、检查确认警告并确认，成功恢复配置；UI 返回站点页后显示该站点 ENABLED。活动 UCI 配置与该备份的 `config-nginx-manager` SHA-256 均为 `072f247675760a19be5b1cee51c4e554da526283f5e222915cc5ff6927c6b8af`，自动生成的 `2026-11-18-060056-pre-restore` 也存在。`nginx -t -c /etc/nginx/uci.conf` 语法检查通过，Nginx worker 仍运行。
- 桌面 1280×820 和全新浏览器上下文的 320×568 视口均保存列表、确认框和恢复后站点状态截图。人工复核：恢复确认警告、取消和确认顺序易读；320px 上提示文字自然换行，确认与取消仍并列可操作；备份行标签与操作按窄屏顺序堆叠，没有插件自有粘连或裁切。本项只关闭该精确候选的备份创建、变更后恢复交互及两个代表视口门禁，不替代全主题/全断点默认矩阵。
- 截图索引及 SHA-256：`luci-four-repo-ui-evidence-2026-11-15/nginx-b028-interaction-2026-11-18/README.md`。仍需完成 Nginx 有效证书/ACME 成功场景和其它仓库待测业务状态。
- **证书状态与 DNS-01 动态凭据布局也已补验。** 在同一隔离容器通过候选 LuCI 表单创建临时自签证书 `ui-gate-valid-cert`（`nginx-ui-gate.example.test`），列表及详情均显示 Valid；检查其剩余有效期和“证书有效并激活”说明后，经页面确认删除。最终设备侧 `nginx_manager.ui_gate_valid_cert` UCI 段不存在，测试证书已清理；`nginx -t -c /etc/nginx/uci.conf` 继续通过。该流程证明有效证书状态的展示及删除清理，不是 ACME 公网申请成功。
- DNS-01 表单对照检查显示，未选 provider 时凭据块隐藏；选 Cloudflare 后生成 API Token、Account ID、Zone ID 三个字段及说明。320×568 下字段纵向分组，LuCI 模态覆盖层可滚动至 DNS Wait、Cancel 和 Create，未裁切。中途未输入或保存任何凭据，没有提交 ACME 请求。桌面与移动截图、SHA-256 已并入上述证据 README。实际 ACME 签发仍待用隔离 ACME 测试端点/可控域名补验；本地未配置可用域名和 DNS 凭据，不把该场景记为 PASS。

### UPnP 向导模式切换和窄屏步骤交互（2026-11-18）

- 用户建议将当前运行 OpenWrt 上的 PM 也用于审计；PM 已按前文记录在主设备实机只读检查、八页复看及 Aurora/Vantage 对照，并作为填充状态证据纳入总 Goal。为避免重跑已有覆盖，本轮继续处理其他仓库尚缺的交互状态。
- 隔离 OpenWrt 24.10.8 容器检查 UPnP 向导时发现：点击 Auto Mode 后，Safe Mode 按钮仍保留 LuCI 原生 `cbi-button-apply` 选中样式，Auto 仅增加未定义样式的 `active` class；视觉选择与实际执行模式不一致。修复仅改 `wizard.js`，切换时同步原生选中类与 `aria-pressed`，未增加主题专属样式。
- 本地工作树修改已通过 `node --check`、`git diff --check`。把精确修改后的 JS 临时复制进隔离容器并清理 LuCI 模块缓存后，在桌面 1280×820 与窄屏 320×568 验证 Safe→Auto→Safe：每个状态均只有对应按钮有 `cbi-button-apply`，`aria-pressed` 与之相符。步骤 1–3 顺序渲染正常，320px 进度点保持单行、文档无横向溢出；纵向滚动后 Previous/Next 与页脚可达。空网络容器没有可供向导选择的接口，因此用浏览器 DOM 内标注为 `eth-ui-gate (test fixture)` 的临时选项与文档地址走步骤 2–3；没有在设备创建接口或改 UCI。没有进入步骤 4，因为 Auto 模式会保存临时 UCI 并执行网络应用。设备 UPnP 保持禁用，`uci changes upnp_nat_relay` 为空。
- 最终源截图及 SHA-256 索引：`luci-four-repo-ui-evidence-2026-11-15/upnp-wizard-interaction-2026-11-18/README.md`。初次源文件烟测时尚未提交／构建；精确候选包在下节完成。步骤 4–10 后续已在可用网络接口的隔离 OpenWrt 上以 Safe 模式完成可见交互复核（详见下方新增记录）；真实 UPnP IGD 成功探测、Auto 模式网络变更、其它业务运行态及其他仓库仍未关闭。

#### UPnP 向导修复提交及候选包（2026-11-18）

- 修复以 `0f57513243f7d341d46c82c5fe955a1cae1e2928` 单独提交并推送至 `fix/footer-full-version`；仅含 `wizard.js` 这一源文件。
- GitHub Actions Build and Release `44251020329` 使用 `publish=false` 完成，两个 SDK 构建均成功、release job 跳过。25.12 APK SHA-256 `bd996510d1ae94fb732a0706e50683617df325e6d5100debd4f4c6863da9b8c4`；24.10 IPK SHA-256 `be5f1ec96474b7076e99eefd9ec4a0a2b05eea61432c3d29229313fe36eaa1fa`。
- 24.10 IPK 安装进隔离容器：最初因容器旧 opkg index 中 `libminiupnpc` 的 checksum/size mismatch 失败；刷新官方 24.10.8 feed 索引后成功安装依赖与候选包。设备内 `wizard.js` SHA-256 `e4bf6206022fafac8c506e16ea43dab0288f060a16f6fe7ee73e58713c3b5db6` 与源文件相同。以包内脚本再次打开向导并切换至 Auto，1280×820 和 320×568 的 `cbi-button-apply`／`aria-pressed` 断言均通过，截图已索引。UPnP 仍禁用，UCI changes 为空。
- Real LuCI UI Gate `44250948304` 精确绑定同一 SHA，已完成：英文、简体中文各 1,686/1,686 PASS、0 errors。每语言覆盖 8 routes × 6 themes × 33 widths + 2 short viewports；Gate 仅覆盖初始步骤，不等价于后续向导步骤与业务运行态。

#### UPnP 候选包全步骤安全交互与 Gate 结果（2026-11-18）

- 新建隔离实例 `upnp-wizard-live-ui-20261118`，以能返回实际 LAN 接口的 PM 专用 disposable OpenWrt 快照启动；没有连接主路由或改变其设置。容器内包源不可达，故本轮未 opkg 安装依赖包；从 Actions 构建 IPK 提取候选数据文件后，设备内 `wizard.js` SHA-256 `e4bf6206022fafac8c506e16ea01dab0288f060a16f6fe7ee73e58713c3b5db6` 与源文件相同。此前另一隔离设备已成功 opkg 安装同一 IPK 并核对相同 SHA。
- 在 Safe 模式按实际 LuCI 交互走完步骤 1–10，测试输入只存在浏览器表单；桌面 1280×820 与窄屏 320×568 每步均采顶部和导航区截图，共 40 张，再额外采集 20 张导航可达性截图。所有状态 `scrollWidth == viewport width`；所有 Previous/Next/最终保存控件均可滚动到达。步骤 10 只检查摘要和“启用服务=否”，没有点击“保存配置”。Safe 模式步骤 4/5 只执行只读检查：实例原配置引用不存在的 `eth2`，所以第 4 步明确显示接口不存在；没有真实下游 IGD，且检查配置中的接口 IP 不存在，所以第 5 步明确显示 IGD 发现失败。这是环境不满足条件的预期结果。
- 结束核验：`upnp_nat_relay.main.enabled=0`，`uci changes upnp_nat_relay` 为空，配置 SHA-256 `15560f9e887df05af47a50637aa0026e0c17d5dbda6d035e684570fe0b2de302`，init 服务 disabled、没有 relay 进程。Auto 模式的 `applyTempUci()` 会保存配置并触发安全应用；本轮未运行，真实网络配置与 IGD 成功态仍待独立安全夹具。
- Actions Real LuCI UI Gate 英文报告 SHA-256 `54fa930158d7c908fb9cf36473ce13503e8b27222ed41ec7259088a408f2970b`；简体中文报告 SHA-256 `48716f23815dba48a8ebaf0e4f29b0659345e45d801e86b089131c17b859180b`。中英文各 48 张 theme-page 联系表（6 themes × 8 routes；33 个常规宽度含断点邻值，以及 320×568、568×320 短视口）均已逐张人工审阅，未发现插件自身裁切、重叠、横向溢出或断点布局异常；Bootstrap Security 告警颜色归属主题原生告警样式。英文 48 张联系表及报告已归档至 `luci-four-repo-ui-evidence-2026-11-15/upnp-wizard-interaction-2026-11-18/real-luci-ui-en/`，含逐文件 SHA-256 清单；自动门禁记录不替代人工视觉复核。
- 隔离截图、逐文件哈希及交互记录位于 `luci-four-repo-ui-evidence-2026-11-15/upnp-wizard-interaction-2026-11-18/README.md`。该克隆中的 LuCI `luci.js` bootstrap 报 `%s/%s.js%s`.format 错误；同一错误在未装 UPnP 包的 PM 基线容器登录页复现，来源属于当前 LuCI 核心运行环境，不归因于 Aurora 或本插件。该错误只作为环境限制留证，不据此改插件样式。

### CFI 隔离设备表单交互补充审计（2026-11-18）

- 在独立 OpenWrt 24.10.8 x86_64 容器 `cfi-ui-goal-20261118` 使用 CFI 当前精确工作树 `b0455209740c14528a610d0c7e248b63c8955807` provision LuCI 页面，不更改 CFI 源码。CFI 服务默认仍为禁用，Rill/LAN publisher 禁用，结束时 `uci changes cf_ip` 为空、服务 inactive。
- 运行仓库已有 Real LuCI interaction script，四项均 PASS：Refresh Sources 保留未保存候选数且不重载页面；Clear Logs 使用 LuCI modal，点 Cancel 无 clear RPC；`prefers-reduced-motion` 下状态提示动画为 none；模拟缺失 cf_ip RPC 后显示 registry error 与 Retry、不露出无表单的 Save/Apply。脚本临时移走 RPC handler 后已在 finally 恢复；设备 handler 复核存在。未认证 LuCI 登录挑战产生预期 HTTP 403；认证后的 Settings 页面无 console errors。
- Settings 页面桌面 1280×900／窄屏 320×568 实测：选择 Custom Schedule 动态显示计划输入；选 HTTPing 动态显示 Data Center Filter；未安装 PassWall/OpenClash 时 Mode 选择器禁用并显示“None (No proxy service detected)”解释。文档宽度始终等于 viewport，手工查看默认、动态字段及底部视图均可读。没有点击 Save/Apply，改动只留在浏览器表单状态。
- 交互测试报告、源图及 SHA-256：`luci-four-repo-ui-evidence-2026-11-15/cfi-interaction-2026-11-18/README.md`。补充审计仅关闭这些具体交互／设置分支，不替代六主题全断点矩阵，也不覆盖来源 CRUD、持久化校验、代理集成、已安装设备或其余业务成功／错误状态；总 Goal 继续进行。

### CFI 自定义来源 CRUD 补验（2026-11-18）

- 在 `b0455209740c14528a610d0c7e248b63c8955807` 对应的 OpenWrt 24.10.8 Bootstrap 隔离克隆中，以 LuCI 原生 GridSection 完成手动 IP 来源新增、名称必填拒绝、编辑为 HTTPS URL、Apply 后重载持久化、删除并恢复空态。URL 使用 `.invalid` 保留为测试值，没有发起网络请求。CFI 主服务和 LAN publisher 始终禁用，没有执行来源刷新／测速。
- 320×568 下确认新增弹窗的字段和 Dismiss／Save 均可见，表格滚动容器自身没有溢出。页面宽度测得 321px；相同 Bootstrap/LuCI 原生系统表单测得 323px，超出元素均为原生 `.cbi-value-field`、`.control-group` 和应用按钮，因此归属主题／LuCI 尺寸舍入，不新增 CFI 补偿 CSS。桌面 1280×900 的空态、有行态及删除后空态均在 CUA 浏览器中截图观察。
- 隔离克隆缺少配置指定的 `/etc/cf_ip/rill-state.json`，首次 Apply 的全局校验因此拒绝提交；创建 root-owned mode-0600 空文件后成功。临时来源 Apply、重载读回及删除 Apply 均完成。收尾从未改动的基线容器恢复配置：SHA-256 回到 `5ed5a0e6dd9b45aee0628a8efe6f898cf44988def69a21b153f35b0f7c082aa5`，`uci changes cf_ip` 为空，主服务与 LAN publisher 均禁用；一次性克隆及 relay 已清理，原隔离容器和主路由未修改。
- 详细交互记录见 `luci-four-repo-ui-evidence-2026-11-15/cfi-source-crud-2026-11-18/README.md`。CUA 截图已在本任务交互记录中人工复核，但未导出为本地 PNG，因此仍需补入持久截图索引；此外这项桌面／窄屏、单主题补验不替代 CFI 六主题 × 两语言 × 断点矩阵，也不覆盖 settings 持久化校验、OpenClash／PassWall 实际表单和 Rill 可用态。
- **CFI Settings 保存／越界校验补验**：第二个一次性 OpenWrt 克隆上，`Download Test Count=101` 的 LuCI Save 被原生范围校验拒绝并显示 `Expecting: value between 1 and 100`；改为 `9` 后 Save 成功，UCI 读回为 9、无待提交变更，CFI 服务继续禁用／inactive。测试副本关闭前从原基线恢复 `/etc/config/cf_ip`，哈希回到 `5ed5a0e6dd9b45aee0628a8efe6f898cf44988def69a21b153f35b0f7c082aa5`。验证过程未触发 CFI 服务或测试操作。错误弹窗和结果页截图已在 CUA 任务轨迹中人工检查，但未导出为 PNG；持久截图证据仍需补齐。详细记录仍见上述 README。此项不替代所有主题／断点的表单矩阵、代理集成实际表单和 Rill 可用态。

### PM 当前运行设备只读复核补充（2026-11-18）

- 按用户建议，将当前运行中的 OpenWrt 也纳入 PM 审计。SSH 只读确认设备为 OpenWrt 25.12.5 x86/64；已安装 `luci-app-performance-manager-all-1.0.7-r1` 与共用的 `rill-runtime-preview-1.5.6-r6`，PM 核心服务正在运行，`performance-manager.main.enabled=1`，`uci changes` 为空。
- 设备上的 `overview.js`、`benchmark.js`、`ui.css` SHA-256 分别为 `30de5b224f553bb8330ee27d7b269fe049911bffa544cfb00a35a03a1de2d851`、`9681279adca3e1d6e4601f92937bba9b566405e89b7b0d10965988b4d3665d7e`、`4d50864e0f71293e4f1cadaea22f525e7e75849eb4b4a1c84e3f1fae4a9d14d5`；与当前 PM 工作树对应文件完全一致。
- 通过已授权会话只读目视了 PM 设置页（Aurora Dark，桌面窗口）：表单仍使用 LuCI 原生字段与分组结构；页内帮助文本和字段间距整体清晰。后续会话过期后重新登录并实机复核了本次更新的智能优化页；概况页仍以完整 Real LuCI Gate 截图验收为准，本轮未单独在主路由打开该页。设备配置与服务均未修改。

### CFI 当前运行设备 OpenClash 页面只读结构核对（2026-11-18）

- 按当前设备实际安装分支打开 CFI OpenClash 页面，仅检查可访问树与元素几何；没有点击备份恢复／删除，也没有保存或重置表单。页面可见配置表单和三条既有备份记录；不记录或传播设备表单里的实际配置值。
- 桌面视口 1298×813 下，页面使用两个原生 `.cbi-section`，各有约 20px 上下内边距；五个 `.cbi-value` 行高约 64px，相邻字段通过 12px 上边距分隔。备份表格宽度与表单内容区一致。此项只确认实际页面结构及几何，不据此单独判定视觉 PASS；仍需在证据包中保留不含设备敏感值的页面截图，并纳入 CFI 主题／语言／断点矩阵。

### CFI OpenClash 备份行内按钮间距修复（2026-11-18）

- 主路由 Aurora Dark 实机只读复核发现，备份表格里“恢复／删除”两个 LuCI 原生按钮直接相邻：按钮边界约重叠 1px，截图中看起来粘连。此问题来自插件直接把操作按钮并排追加到单元格，没有建立按钮组间距，不归因于主题。
- 候选 `5d8c8783995ba15bc318a8c8886df4879a2ff7b2` 将按钮放入插件自有弹性操作组，使用 `.5em` 的间距并允许窄屏换行；按钮颜色、外观仍由 LuCI 主题控制。Real LuCI Gate 加入操作间距测量，并在隔离代理路由夹具里创建三条无敏感内容的备份，以保证检查覆盖有数据状态。
- 对英文代理分支截图联系表进行人工审阅时，另发现 320px 宽下三个冗余表头挤成连续文字；LuCI 移动表格已经逐格显示 `data-title`。因此 `a092ec2bb3d04d8817ebd480e40f944c35f4cbf4` 增加专属表格类并在 600px 以下隐藏重复 `<thead>`，门禁也断言窄屏表头已隐藏。此为插件自有结构问题；继续复用 LuCI 默认配色和数据格样式。本地 `node --check`（门禁 JS、OpenClash view）、`git diff --check` 通过。
- 当前精确提交 `a092ec2` 已推送到 `audit/cfi-footer-spacing-20261116`。同一个最新 SHA 的英文／中文 Real LuCI Gate 分别为 `44303586471`、`44303598148`；两者完成后还需逐主题人工审阅全断点联系表、构建此 SHA APK、在主路由安装并只读复验，再记录 UI 修复 PASS。此前提交 `5d8c878` 的英文门禁 `44296321868` 的报告为 462/462 代理路由组合通过（6 主题 × 36 宽度及 2 个短视口），但因为人工视觉复核新增了上述窄屏表头修正，该批结果不作为最新候选的最终验收。完整四仓 Goal 继续进行。
- 最新提交 `a092ec2` 的 x86_64 25.12.5 SDK LuCI APK 构建 `44303859857` 已成功；产物 `luci-app-cloudflare-ip-2.6.2-r17.apk` SHA-256：`fcea5a903c1a10aeb85b04656e909b6e61324e233e569da137d4c11fe6416bb4`，Rill companion SHA-256：`b3299fc5d5ed2c1a94b68c9387935dbd03c4c7a941abaae016873dc34964bf20`。下载到证据目录 `cfi-run-44303859857/`；等待中文截图矩阵完成后再启动单独英文矩阵（同 workflow 只允许一个实例），并在所有最终验收通过后安装此包。
- 最新提交完整 CI `44303561008` 通过，包含 host contract、OpenWrt 多目标包构建和运行时集成检查；UI Gate 中文仍在矩阵截图步骤中。
- 最新候选中文 Real LuCI Gate `44303598148` 已通过，SHA `a092ec2`。完整基础矩阵 1,830 行：1,374 PASS、456 N/A（基础环境未装 OpenClash／PassWall 可选路由）、0 FAIL；代理表单分支 462/462 PASS。OpenClash 路由 228 个组合的操作按钮最小间距 7px、最大 8px；<=600px 的 72 个组合表头全隐藏；全部 0 横向溢出／截断／console route errors。证据包 `cfi-run-44303598148-zh/real-luci-ui-evidence-run-44303598148-attempt-1/` 已下载，两份报告引用的 2,292 张截图均存在；六主题×各断点的 OpenClash、PassWall 联系表均已人工审阅，暂未见新插件自有布局缺陷。英文同 SHA 门禁仍在运行。
- 英文最新 SHA 门禁已启动：`44311538731`（中文先跑，避免被同 workflow 并发策略取消）。
- CI `44296287752` 收尾后确认：host/package/UI 相关检查通过；Rill 同版本 Runtime 集成因全局 `LD_LIBRARY_PATH` 污染宿主 `dirname`/`mktemp` 调用而未执行到测试，属于既有 CI 环境脚本问题。已用 Runtime 专用 wrapper 隔离动态库环境，修复提交 `547c4bf` 的精确 SHA CI `44299131209` 全部成功，包括 host contract、四个 OpenWrt 目标包和 Same-release generic Runtime integration。首次 CI 的发布资格 guard 另因计划已记录的 Stable upstream tag 漂移失败，不能把它归为 UI 改动回归，也不能据此覆盖 Stable Runtime 的资格要求。

### PM 受控 A/B 完成态响应式复核补充（2026-11-18）

- 按计划在隔离 OpenWrt 24.10.8 实际运行 LuCI 进行受控 A/B 结果态复核，不触碰主路由。当前 PM 源文件在设备与 `1aab592c69b7cfcf5e9fbf83f4f06013a3c5cb4d` 工作树一致。会话 `bench-95a7e223-73612820` 经真实 LuCI 表单完成基线和候选 iperf3 3.22 本地端点测量，健康检查通过并自动回滚；设备内核值恢复为 `net.core.rmem_max=7500000`。
- Aurora Dark 中文下在 1280×900、640×900、320×568 复核结果页面。可见阶段结果、成功提示和 JSON 折叠区；320px 下纵向排布且文档宽度等于 viewport，无横向溢出。手工截图和哈希索引见 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-benchmark-stage-r11/final-result-ui-2026-11-18/README.md`。这是结果态的额外通过记录，其他 PM 页面／主题／动态状态仍按总矩阵验收。
- 测试曾在隔离容器临时延长提交确认时间，结束时已恢复至 30 秒。性能管理器配置文件哈希回到原基线 `92e79b01a0961e8708f2ff7c706c3a5d23c4f553adc0bcdfd8a188f61ef6ff48`，`uci changes` 为空，`rmem_max` 回到基线；主路由始终只读。

### PM 智能优化页信息卡密度复核（2026-11-18）

- 根据真实 LuCI 视觉复核，隔离 OpenWrt 返回的无建议/本机仅检测到原生数据包转向状态下，智能策略卡和唯一的提供方观察卡原先上下各占整行，桌面产生过多空白。属于插件信息排布问题，不是 Aurora 主题缺陷。
- 将策略摘要、可执行建议和观察卡并入同一 `pu.grid()`，沿用 PM 已使用的主题变量响应式 LuCI section 网格；未增加私有配色或控件覆盖。候选 `810744a18313cde2495235f20b443cf7654e5fde` 在临时 OpenWrt 中实测：Aurora Dark 中文 1280×900 并列，320×568 纵向堆叠，页面宽度无溢出。截图、SHA 和限制见 PM 仓库 `luci-four-repo-ui-evidence-2026-11-15/pm-benchmark-stage-r11/final-result-ui-2026-11-18/README.md`。
- 本地 PM 198 项 unittest、`node --check optimize.js`、`git diff --check` 通过。精确提交 CI `44269458551`、LuCI UI SDK 包构建 `44269458494`、多架构包构建 `44269458627`、Real LuCI UI Gate `44269458585` 正在运行；待所有精确 SHA job 结束、人工复核中英文/六主题全宽度截图并安装精确候选包后，再关闭此布局修正。

- **PM 智能优化页真实 Rill 多卡状态修订（2026-11-18）**：主 OpenWrt 的实际返回有两个观察和一个 Rill `noop` 建议，导致孤立卡片布局，并重复“保持当前配置”语义。提交 `982e9f8` 把 Rill 权限、执行路径、置信度和技术详情并入智能策略卡。复核 Bootstrap 两列状态发现观察项仍形成孤卡，故在后续提交 `acd9646563ce28ba7db2e4a51a437d327626acba` 将两项观察收进“系统观察”原生 LuCI 卡片，并把 no-op 标题简化为“Rill 建议”；英文与简体中文 PO 同步。198 项 unittest、JS 语法、PO 目录一致性、`git diff --check` 通过。
- 精确 SHA 的 CI `44280939581`、LuCI SDK 包构建 `44280939585`、三架构 All-in-One 构建与证据 `44280939695` 全成功。Real LuCI Gate `44280939600` 英文/中文均成功：每语言 1,968/1,968 行通过、0 错误；覆盖 8 个 PM 路由、6 种主题配置、39 个常见及断点相邻宽度和两个短视口。各语言另有 2,064 张截图（含性能测试状态图），报告与校验和在 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-benchmark-stage-r11/real-luci-ui-44280939600/README.md`。
- 另以隔离 OpenWrt 和真实多卡 Rill 状态完成 492 个断点渲染检查，六主题×中英文均通过，无单独 Rill 卡、两观察项成组、无文档横向溢出或浏览器错误；截图与审阅结果在 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-benchmark-stage-r11/rill-advisory-fixture-2026-11-18/README.md`。并在主 OpenWrt 实机以 Aurora Dark 中文复核 exact-source 页面，标题呈现为“Rill 建议”和“系统观察”。
- 精确 x86_64 All-in-One APK SHA `eda5069c38be2d0c463a59f14f98cd78fa4c3f15ebd6d06eac09a21e75a94d26` 已安装；设备内 `optimize.js` SHA `6a45375068074d0bbf29fe9a9b4e77e6952c697c992be3d29adbf12b805334b7` 与候选一致。PM service 仍运行，配置 SHA 保持 `19bf0cd88577fca49e0902633d0fc8a38beb480ae1297d00433b888c1da1a505`，`rmem_max=8388608`，共享 Rill binary SHA 不变，`uci changes performance-manager` 为空。运行中 PM 自审计记录见 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-benchmark-stage-r11/pm-self-audit-2026-11-18.md`。此项修订及验收关闭；四仓总 Goal 仍按后续任务继续。

### CFI `a092ec2` 英文 OpenClash 精确候选人工视觉复核（2026-11-18）

- Real LuCI Gate run `44311538731` 对应 SHA `a092ec2bb3d04d8817ebd480e40f944c35f4cbf4`，英文代理集成分支 462/462 自动 PASS。针对该候选所改 OpenClash 备份操作组和移动表头，逐行人工审阅全部六个主题、36 个标准宽度及两个短视口，共 228 行 PASS。320px 下 Restore/Delete 有清楚间距；600px 隐藏重复表头，601px 恢复表头；行内标签保持可辨识。未见插件自有溢出、裁切、重叠或页面横滚。
- 审阅台账：`luci-four-repo-ui-evidence-2026-11-15/cfi-run-44311538731-en-openclash-manual-review.csv`（SHA-256 `0d7a17ca9b1a45aa78a5a619c4066611ef374965e5c5fb6f00c97e8cd7220744`）；截图与抽查图哈希索引：`cfi-run-44311538731-en-openclash-manual-review.md`。这只关闭本次 OpenClash 英文精确候选的布局视觉项，不关闭 CFI 交互、装机或四仓 Goal。

### PM 最终候选断点矩阵补漏（2026-11-19）

- 人工审阅 `af87733` 英文 Overview 六主题联系表时发现其新增的 `min-width:27rem`（432px）状态块断点没有进入原视觉矩阵；原矩阵在 430px 后直接到 599px。旧的 1,968 PASS 不能覆盖 431/432/433px，因此尚不作为这一断点的人工验收。
- 新增独立真实 LuCI 门禁 `tests/real-luci-ui-overview-breakpoint.cjs`，逐主题捕获 431、432、433px Overview，并验证状态卡数量、实际网格列数、文本完整性、无横向溢出及主题加载；工作流 `real-luci-ui.yml` 在双语主矩阵后执行。未改动已有未提交的 `tests/real-luci-ui-visual.cjs`，也未修改 PM 运行时代码。
- 工具变更提交 `62a3c64fd4bfb0e5070b66d2da1a219523febe05` 已推送；Real LuCI UI Gate run `44343488359` 已触发，当前 queued。该 run 的报告 SHA 会是工具提交；PM UI/APK 源码仍绑定 `af877339d3a30ced664cc96101a0f43ebf47724c`。须等中英 36 项新边界截图跑完并人工复核后，才可完成 PM 概况布局项。
- `af87733` 英文全矩阵已下载并校验：报告 SHA-256 `551be5f55db96524dfba8e9283c25ae43e9ba4a11ffa44bdfc874cfca29b50b1`，报告绑定 UI source `af877339…`，1,968/1,968 PASS，1,968 张引用截图全存在；六主题 Overview 全视口联系表已审阅。完整截图与联系表目录：`pm-overview-grid-af87733-run-44333468185/en/`。报告矩阵缺新 432px 断点的观察仍成立，待上述补测取代。
- 英文全矩阵的 1,968 张 exact-source 截图路径完整，Overview 246 行已逐主题／视口写入视觉审阅台账 `pm-overview-grid-af87733-en-overview-review.csv`（SHA-256 `5f134d17a28129298e57c842ac4d7f59229d46ef1a8f91c71f8d598823ef6983`）。人工复核确认 430px 单列、599–601px 两列、1024px 起四列，320×568 短屏和 1920px 宽屏均未见裁切；431/432/433px 留待新门禁。
- 主 OpenWrt PM 仅做只读前态记录：OpenWrt 25.12.5 x86/64，`luci-app-performance-manager-all` 已安装、PM 服务 running；现有 overview.js/UI CSS 哈希为 `30de5b22…` / `4d50864e…`，配置 SHA-256 `19bf0cd88577fca49e0902633d0fc8a38beb480ae1297d00433b888c1da1a505`，`rmem_max=8388608`。这不是 `af87733` 候选的装机证据。候选安装保持待办，且不在主路由上更改 PM 配置或服务。
- Run `44343488359` 当前进展：英文 job 在 `Install Playwright and locate Chrome` 步骤失败，未进入矩阵；简体中文 job 已进入全量截图。保持中文 job 完成后读取已终止英文 job 的日志，只重跑英文 job；此失败不构成界面 FAIL，也不能代替 431/432/433px 的视觉结果。
- CSS breakpoint audit found the same gap at the 64rem/1024px four-column transition: the main matrix included 1024px but omitted 1023/1025px. The focused test now covers both changed boundaries at 431/432/433px and 1023/1024/1025px (six viewports × six themes × two languages = 72 screenshots), with expected 1/2/4 column counts. Test-only commit `288276ee94c252be902960b0827239aebfa40945` pushed; exact Real LuCI run `44345769379` queued. Earlier run `44343488359` is superseded and cannot provide final sign-off.

### PM 候选包隔离设备桌面复核更新（2026-11-19）

- 更新此前“PM 候选安装待办”的状态：将精确 `af877339d3a30ced664cc96101a0f43ebf47724c` All-in-One 包装入独立 OpenWrt 25.12.5 x86/64 容器 `pm-af87733-candidate-20261119`，服务运行；容器页面内 `overview.js` 与 `ui.css` SHA-256 均与候选工作树逐字节一致。活动 PM UCI 配置 SHA 保持默认 `19bf0cd…`，`uci changes` 为空；期间意外形成的 LuCI Attended Sysupgrade 提示偏好变更已恢复，未保存，未触碰主 OpenWrt。
- CUA 已在实际 LuCI 页面人工复核 1280×720 中文概览：Bootstrap 原生页面样式下四个状态块各 285.25px、间隔 13px；状态标签与较长说明完整显示，文档无水平溢出；摘要、信息表、状态和页脚均正常渲染。此为安装后桌面抽查，不能替代所有页面/主题/断点验收。截图在 CUA 当前任务交互结果中完成查看，尚未持久导出为 PNG。
- 单独的 Real LuCI UI Gate run `44345769379`（工具提交 `288276ee94c252be902960b0827239aebfa40945`）截至记录时仍由英文 job 采集全矩阵，中文 job queued。门禁扩展了 Overview 的 431/432/433 与 1023/1024/1025px 精确边界，六主题、两种语言，72 张专门断点截图；必须等 run 结束并人工审阅后再关闭 PM 概况项。主 OpenWrt 仍保持只读。
- Run `44345769379` 2026-11-19 update: English 1,968-row full matrix succeeded; its 36-row targeted boundary step produced all screenshots and correct layout metrics but exited on six first-431px browser-error checks traced to the stock LuCI home page loaded immediately after login, not PM Overview. All six English contact sheets are manually reviewed and their 36-row visual ledger is preserved under `pm-overview-breakpoints-run-44345769379-en/`. Corrected test harness is committed locally as `9a51bf5`; it is not yet pushed because the Chinese full matrix under the old commit remains in progress. After that run finishes: retain/review Chinese artifacts, push the tooling fix, run a fresh bilingual exact-source check, and review the new six-theme/36-width output for each language before closing PM layout.
- Chinese target-run result is now retained and manually reviewed in `pm-overview-breakpoints-run-44345769379-zh_cn/`: 36/36 screenshots and six themes reviewed; 431px one-column, 432/433px two-column, 1023px two-column, 1024/1025px four-column. It shares the same harness-only browser error at the first 431px capture; no layout metric failed. The former run `44345769379` has both full language matrices successful, but both targeted test steps exit on those login/home warnings. Pushed tooling fix `9a51bf560fce18afe892a05a8c99c7e6cbbfa687`; exact new bilingual gate run `44355336447` queued. Do not close PM layout until that fixed run and manual screenshots pass.

### PM 候选智能优化与性能测试实机补充（2026-11-18）

- 在隔离 OpenWrt 25.12.5 候选实例 `pm-af87733-candidate-20261119` 中，使用精确候选包只读复核智能优化页和性能测试待机页；未展开技术折叠、未启动测试、未保存配置。智能优化页呈现策略、Rill 建议与系统观察三个明确语义组；性能测试页的测试动作与评估路径并列，测量类型和开始按钮成组；两页在 Bootstrap Dark 下均未见主题色硬编码、文本裁切或页面横向溢出。此为两个新增改动页的桌面状态抽查，不替代 `44355336447` 的全量主题、语言和宽度矩阵，也没有导出持久 PNG，不能单独关闭其审阅项。
- 当前 PM 候选 `af877339d3a30ced664cc96101a0f43ebf47724c` 相比此前已审阅源 `07f03a9029c494a8ee7c55c395a7c57eda4b2e36` 实际改变 `overview.js`、`optimize.js`、`benchmark.js`、`ui.css`、`ui.js`；因此三页均须绑定此候选复审。精确门禁 run `44355336447` 绑定修正后的工具提交 `9a51bf560fce18afe892a05a8c99c7e6cbbfa687`，英文主矩阵仍运行、中文 job 排队；关闭前需下载并检查对应截图、审阅 Overview/Optimize/Benchmark 改动页及六个 Overview 边界邻值，再核实最终候选装机证据。
- 候选容器五个资源文件均已逐字节对照：`overview.js` SHA-256 `aec205bb9aaca8d24c57da033bc0ef718b2c3537e6d3b6760fab204ac3f4e3c4`、`optimize.js` `6a45375068074d0bbf29fe9a9b4e77e6952c697c992be3d29adbf12b805334b7`、`benchmark.js` `9681279adca3e1d6e4601f92937bba9b566405e89b7b0d10965988b4d3665d7e`、`ui.css` `901011c497d593d279b1a92d3a76d1f25325f8ae0e8b6e34e411b70b8a98cccd`；`ui.js` 在按包构建规则将 `@PKG_FULL_VERSION@` 替换为 `1.0.7-r1` 后与设备文件逐字节相同，SHA-256 `23239aea540dc192e5db42e73609ebf13635a7dcdf54556f7c0021169ec08d26`。因此该隔离装机实例确实包含上述 exact candidate 页面资源。

### PM exact candidate双语视觉矩阵复核（2026-11-19，run 44355336447）

- 修复门禁工具 SHA `9a51bf560fce18afe892a05a8c99c7e6cbbfa687` 的 Actions Real LuCI Gate `44355336447` 双语 jobs 均完成成功。PM UI 资源精确绑定候选 `af877339d3a30ced664cc96101a0f43ebf47724c`；中英文各覆盖 8 个视图 × 6 种主题模式 × 39 个 CSS 宽度及竖屏／横屏短视口，分别 1,968/1,968 PASS、零错误与零浏览器错误。
- Overview 专项断点补测每种语言各 36/36 PASS：431px=1 列，432/433px=2 列，1023px=2 列，1024/1025px=4 列；状态项均完整，无横向溢出。中英六主题的 36 张图均已人工复核。
- 英文和中文 Overview、Optimize、Benchmark 的 18 个主题联系表（每语言 702 个常规宽度画面）、短视口汇总表及六主题 Overview 边界汇总图已人工复核；另查看了 Aurora Dark 中文桌面 1280px 三个改动页全页图和短屏全页图。未发现插件造成的裁切、重叠、意外换行或页面横向溢出。English/Chinese 行级记录、JSON 报告、联系表与校验清单分别归档于 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-run-44355336447-en-manual-review/` 和 `.../pm-run-44355336447-zh-manual-review/`；Actions artifact id `14451873862`（EN）、`14455921951`（ZH）。
- 新增受控 A/B 成功／未验证回滚结果态的跨主题断点视觉夹具，不向设备服务转发任何 `benchmark_start` mutation。提交 `908012277470fe0e6bb91303f953f46e056de367` 已推送；Real LuCI run `44363269397` 正在执行，待中英各 492 个结果态截图完成及人工复核前，**阶段 1 仍不关闭**。同 SHA CI `44363269651` 成功；多架构 All-in-One run `44363269348` 的 armv8 成功，x86_64/Filogic 编译仍进行中。既有精确候选包装入 `pm-af87733-candidate-20261119` 的隔离实机证据不被此次测试提交改写。
- `9080122` 对应 All-in-One run `44363269348` 三个目标架构（armv8、x86_64、Filogic）及 release assembly dry-run、证据组装全部成功；CI `44363269651` 已成功。该提交未修改 `package/luci-app-performance-manager` 下任何运行时代码（与精确 UI 候选 `af877339…` 的 package 子树 diff 为空）。PM 仍仅等新增双语受控 A/B 结果视觉矩阵及人工复核关闭阶段 1。

### PM 受控 A/B 结果态视觉门禁复测（2026-11-19，诊断修复后进行中）

- 前一轮 exact UI package `af877339d3a30ced664cc96101a0f43ebf47724c` 的 bilingual run `44363269397`：英文和简体中文全页矩阵分别 1,968/1,968 PASS，Overview 专项断点分别 36/36 PASS；两边新增的受控 A/B 结果态步骤均在等待完成提示时失败，不能将结果态行记为 PASS。
- 已下载并核验失败 run 两份 Actions artifact：EN artifact ID `14458855953` digest `f6d1e52eaeb19d199efe52f904fcf5f9479601d3a2593530a6d425309998a552`；ZH artifact ID `14458499670` digest `b778818bef241473351a99d53719403e731dc76ac4b768c7f65189574334c351`。报告确认两种语言主矩阵各 1,968 PASS、断点各 36 PASS，benchmark-result 报告各因开始状态未显示预期完成提示而无截图行。
- 在本机一次性 OpenWrt 24.10.8 克隆中定位到 fixture 没有拦截实际请求：LuCI 发到 `/ubus/`，旧拦截 glob 错写成 `/cgi-bin/luci/admin/ubus`，所以点击按钮曾真实启动了隔离设备上的 `awaiting_control` 测试会话；该动作未应用系统优化或改变配置，容器随后移除。修正为只拦截 `/ubus/` 下 `performance-manager.benchmark_start` 的 `phase=begin` 请求，随后本地英文 Bootstrap Dark smoke matrix 6/6 PASS。
- 初次 smoke 修正拦截后发现第二个夹具断言错误：原生状态徽标由主题以 CSS 大写显示 `COMPLETE`，脚本原用区分大小写的 `/Complete/` 误报 rollback/stage 不完整。改为大小写不敏感匹配。人工审阅 320×568 中文版以外的英文有效／未验证结果截图及 1280px 桌面截图：阶段状态、rollback 标签、成功／警告说明均完整，移动布局纵向清楚，无横向溢出。
- 已加入诊断输出（ubus method / phase、可见主内容、浏览器错误和失败截图），并在 `.github/workflows/real-luci-ui.yml` 增加仅 benchmark-result 门禁入口，便于对 492 个每语言状态画面单独重跑；`actionlint`、`node --check`、`git diff --check` 均通过。工具提交 `0d4460fc6902701dd231cbad5eaab17b6ce6cdbf` 已推送。经 `git diff --exit-code af87733..HEAD -- package/luci-app-performance-manager` 证明 package 运行时代码无变化。
- 新的 bilingual result-only Actions run `44374132753` 已启动（workflow dispatch `benchmark_result_only=true`），待英中各 492 状态截图报告完成及人工复核前，阶段 1 仍保持未关闭。推送自动触发的全矩阵 run `44374094953` 已由同 workflow concurrency 取消/收敛，不作为本轮证据。
- 本地 smoke 截图、report、README 与 SHA256SUMS（6/6 PASS，明确为 diagnostic smoke，不能替代 Actions full result-state matrix）位于 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-benchmark-result-fixture-smoke-2026-11-19-en/`。

### PM 受控 A/B 结果态门禁通过（2026-11-19，run 44374132753）

- **阶段 1 性能管理器界面：PASS，现可进入/继续阶段 3。** 结果态专用 Actions run `44374132753` 对 exact UI 候选 `af877339d3a30ced664cc96101a0f43ebf47724c` 完成中英文截图矩阵；英文 artifact `14460401754`，SHA-256 `d956005faa39fda249648f5d4f6641d173af5b8839938119c9c08c0ccc73caae`；中文 artifact `14460817091`，SHA-256 `33f56eeee09ba63aeb98987bf933b348c5cc506287fca4f11358a85d544317c1`。每种语言 492/492 PASS，涵盖六种主题模式、成功/未验证两种回滚情景、39 个 CSS 宽度和两种短视口，零截图错误。
- 已人工复核两种语言各 12 张主题×情景联系表（共 24 张），并检查代表性的 320×568 与 1280×900 原图；未发现 PM 自有布局的裁切、重叠、横向溢出或窄屏状态说明不可读。行级 492 项审阅清单、报告、联系表及校验清单分别归档于 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-run-44374132753-en-result-review/` 和 `.../pm-run-44374132753-zh-result-review/`；两份 SHA256SUMS 已验证全部文件匹配。
- 本地 OpenWrt 24.10.8 隔离实例上的英文 Bootstrap Dark 控件拦截 smoke 为 6/6 PASS；此前 exact candidate 的隔离 OpenWrt 25.12.5 安装和 PM 八页全量双语主题/断点矩阵见上一节。本轮只改测试夹具与 workflow，没有改变 PM 运行时代码；候选 package 子树与 UI 候选 commit 的差异为空。保持用户原有未提交的 `tests/real-luci-ui-visual.cjs` 修改及各未跟踪证据文件，不纳入工具提交。
- **未完成范围仍是阶段 3。** 四仓库剩余独立视图、子状态及真实交互需要逐项绑定当前源码、补拍/审阅所需矩阵，并完成候选 Actions 构建和本地 OpenWrt 联合安装验收；阶段 1/2 PASS 不代表 Goal 完成。

### Nginx 主路由候选资源精确复核（2026-11-19）

- 对主 OpenWrt 已安装的 `luci-app-nginx-manager-1.8.11-r22` 做只读包归属与资源哈希复核，`sites.js`、`certificates.js`、共享 `nginx-manager.css` 均与本地精确候选 `b028d67a926260b0a54d381791bb6067e1e23843` 逐字节匹配；该精确提交的 SDK Actions 构建 `44209203157` 成功。因设备已含候选文件，本次未重装。
- Nginx `b028d67` 的双语全视图／主题／断点默认态矩阵和人工截图审阅已完成，备份恢复与临时自签证书验证另有隔离设备记录。仍未覆盖真实公网 ACME 成功申请（没有可控 DNS 凭据），这项与其余仓库业务状态、全仓最终联合装机一起保留在 Goal 未完成清单中。

### PM 当前运行设备复核补充（2026-11-19）

- 按用户建议，再从 Edge 登录当前运行的 OpenWrt 25.12.5，查看 PM 概况实际页面。设备上页面自报 PM `v1.0.7-r1`；服务运行、健康保护通过、配置状态说明“部分推荐的测试和诊断工具尚未安装”、Rill 显示可用。四个首屏状态块在当前主题下均完整，配置状态块也能解释其状态原因；系统信息表、最近事务、路径卡片与页脚可见。
- 该轮仅查看只读概况，没有触发优化、保存配置、运行基准测试、回滚或更改主题。右侧悬浮工具条覆盖视口边缘属于 Aurora 主题层表现，遵守用户归因边界，不加插件补丁。此设备截图未导出持久 PNG；它补充实机当前状态观察，不替代上述候选包/截图矩阵证据。
- 当前 Goal 完成度按三阶段及阶段 3 已核实子项估算约 **70%**；未完成部分约 **30%**，主要是阶段 3 四仓库其余页面状态、交互流程和最终候选包联合装机验收。此比例为工作量估算，不是逐截图行数比例。

### CFI `a092ec2` 主路由候选资源对应性复核（2026-11-19）

- 主 OpenWrt 已安装 CFI `2.6.2-r17`，与成功的 x86_64 25.12.5 SDK 构建 `44303859857` 对应产物版本一致。候选 APK SHA-256 为 `fcea5a903c1a10aeb85b04656e909b6e61324e233e569da137d4c11fe6416bb4`。
- 通过设备只读比对，运行中的 `openclash.js` 与候选 `a092ec2` 源码 SHA-256 均为 `2acf67b23d3cc935cef450add97a0740752667f18b77376fa0fbc01ee392b33c`；共享 CFI 样式 SHA-256 均为 `38867fe85829b69aac6d1710e838dea41e089f8a8a6e187318fa1af8ab4da579`。因此最近的 OpenClash 按钮间距和窄屏表头修正已经出现在主路由实际运行的 PM/CFI 同机环境中；本次未重装或改动设备。
- 此次核验只证明该候选 UI 文件部署及先前矩阵证据的源码对应性，不替代 CFI 尚未完成的交互覆盖和四仓联合验收。
- `a092ec2` 英文精确门禁 `44311538731` 默认矩阵为 1,830 行（1,374 PASS、456 个可选代理依赖缺失的 N/A），安装代理夹具的两页分支另有 462/462 PASS；中文精确门禁 `44303598148` 也通过相同行数。和前一轮已逐行人工审阅的 `b045520` 中英文矩阵相比，此提交仅新增 `.cfi-table-actions` 间距、OpenClash 专属移动表头隐藏、对应页面操作容器及 CSS cache-buster；共享样式改动的选择器仅作用于表格操作和 OpenClash 备份表格。因此其它七个视图延续原有全宽度／六主题人工审阅；OpenClash 英文本次精确截图 228/228 已逐行审阅，中文对应六主题各宽度联系表已有记录复核。CFI 默认页面视觉矩阵可通过，尚待处理的是矩阵声明的业务交互覆盖及四仓最终联合验收。
- 同一精确候选真实 LuCI 交互门禁另通过 4 项：来源刷新保留未保存草稿、清理日志取消不产生副作用、减少动态效果偏好关闭状态动画、RPC 被拒绝时明确显示错误和重试而不是空状态。证据位于英文 Actions artifact 根目录 `ui-gate.json`；该交互步骤会故意制造两个预期 403 记录，不属于未处理的浏览器故障。

### PM 精确候选装入主 OpenWrt（2026-11-19）

- 主 OpenWrt 原来运行的 PM 概况文件仍是较旧 SHA。将成功的 All-in-One 构建 run `44363269348` 的 x86_64 APK（`9080122` 工具 SHA，对应 PM package 子树与精确 UI 候选 `af877339d3a30ced664cc96101a0f43ebf47724c` 一致）同版本 force-reinstall 到主设备。APK SHA-256 `ada4ddba49ecc6ab403dc23db0f541dc16ba19eea375f09b1b7324afb69fdca9`，构建 manifest 与 checksum 文件已留存。
- 安装后 `overview.js`、`optimize.js`、`benchmark.js`、`ui.css` 均逐字节匹配 `af87733` 源码；PM 服务保持运行，配置哈希不变，uci changes 为空；`rill-runtime-preview` 仍是单独共享 provider，运行时二进制 SHA 不变。浏览器重载候选 Overview 后，实际状态卡、系统信息、健康保护、事务和路径均显示正常，未做测试、保存、回滚或改主题。
- APK、manifest、设备核验报告与 SHA256SUMS：`luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-final-install-9080122-2026-11-19/`。本项补齐 PM 最终 UI 候选在主 OpenWrt 的精确安装和概况检查，不关闭阶段 3。

### 四仓候选包同机共存抽查（2026-11-19）

- 同一台 OpenWrt 25.12.5 已安装 PM、CFI、Nginx Manager、UPnP NAT Relay 四候选包以及独立的 `rill-runtime-preview` provider；从设备校验四仓关键页面／样式文件与各自 exact candidate 构建源哈希一致。PM、Nginx、UPnP 服务保持运行，Rill 二进制哈希与安装记录相同。
- Aurora Dark 中文约 1298×813 的 Edge 实机中逐一打开四个 Overview，状态区、LuCI 主题卡片、服务控制组、信息块和页脚的视觉顺序一致；CFI 的三张统计卡、其余页的四张统计卡均按各自字段自然排布，无插件自有的粘连、裁切或页级横向溢出。没有点击服务控制或修改设备状态。
- 哈希清单、验证范围和限制见 `luci-four-repo-ui-evidence-2026-11-15/joint-device-candidate-coexistence-2026-11-19/`。截图未持久导出；这是同机桌面共存补充检查，不替代双语、六主题、逐宽度截图矩阵及其余交互态证据。
- 同一只读实机检查继续打开 UPnP 填充映射表：13 项源映射及 13 项活跃同步行均完整显示，原生表格列和状态易读。没有点击同步、刷新、清理或停止；也没有把地址、端口、设备描述等映射内容保存在证据中。此项仅补齐真实填充态的桌面可读性，移动宽度需由隔离夹具矩阵覆盖。
- 向下滚动到页面底部后，拒绝映射空状态和页脚均可到达；页脚链接背景在当前 Aurora Dark 桌面视口中紧贴图标／文字。作为同机实视补充，没有持久截图；全主题页脚矩阵仍是判定依据。

### UPnP 新模式选择门禁延迟与下一轮修正（2026-11-19）

- Actions Real LuCI Gate `44379124801`、SHA `a065bce0d7c9db2623c067e7a8abae0bade69da4` 在 2026-11-18 19:18 UTC 启动；英文 job 后续失败，中文 job仍卡在 `Install LuCI runtime and declared package dependencies`。run 整体尚未结束，所以 GitHub 仍不开放失败日志；不能将未完成门禁视为 PASS。
- 复查 workflow 后发现 `opkg` 状态轮询有界，但启动后台命令的 `docker exec -d` 没有自身超时。添加 15 秒启动超时并把启动错误纳入 update 重试的修复，已在独立分支提交并推送（`80b271f86b549de42f9ce373f38781a9109b638f`），不是对原 UI/package 源码的修改。静态校验 `actionlint`、对应 shell block 的 `bash -n` 和工作树 `git diff --check` 均通过；真实 Actions 运行结果见后续状态节。
- 修复分支 run 结束后需确保英文、中文两语言都取得精确截图矩阵 artifact，逐主题审阅 wizard selected-mode 状态。当前因同 ref 重复触发，修复分支 run 的中文 job 已取消；该矩阵需在 run 终态后重跑，旧 run 继续监控并读取可用日志。

### PM 最终候选主路由只读复看补充（2026-11-19）

- 在主路由已安装的 PM `af87733` 最终候选上，以 Aurora Dark、中文、Edge 桌面约 1298×813 只读打开「智能优化」和「性能测试」。优化页的策略摘要、Rill 建议、系统观察和技术详情折叠项均完整；测试页动作／路径／测量类型选择器及开始测试入口均可读，未点击开始测试、未保存或改配置。该观察仅补充安装包页面健康信息；本轮截图未导出归档，不替代对应的真实 LuCI 双语／六主题／断点截图矩阵与人工审阅。
- 两页首次异步载入时短暂显示「正在载入视图…」，稍后均完成渲染。页面底部 PM 社交／项目链接和 LuCI 页脚在当前 Aurora 桌面视口可见；主路由悬浮工具条属主题显示层，本轮未处理主题本身问题。

### PM 主路由其余页面只读复看（2026-11-19）

- 同一已安装候选、Aurora Dark 中文桌面环境继续检查「能力」「Rill 智能」「历史与回滚」「高级」「设置」五页。能力页可读显示可用／未知／不可用状态卡；Rill 页显示运行时可用、建议/冷启动状态、排名、反馈与高级详情入口；历史页显示已有事务及事务详情、回滚入口；高级页运行状态、资源使用和诊断区完整；设置页的 CBI 基本表单、Rill 运行时字段、主题原生分页及保存栏可见。
- 全程只导航、展开范围内的只读信息并滚动检查；未更改开关/选择、未点刷新、保存、应用、重置或回滚。历史页已有事务明确视作设备原有状态，不作操作。
- 以上截图在 CUA 任务过程人工目视，但未持久导出 PNG；此项只补充 PM 精确包在主路由的八页桌面运行态检查，不替代已归档的双语六主题全宽度矩阵和交互/业务状态验收。

### UPnP Real LuCI Gate 启动超时修复分支状态（2026-11-19）

- 工具修复提交 `80b271f86b549de42f9ce373f38781a9109b638f` 已推送至独立分支 `codex/upnp-dependency-start-timeout-20261119`，仅修改 `.github/workflows/real-luci-ui.yml`。自动 run `44387246806` 曾进入英文依赖安装后也被取消，最终整个 run 为 `cancelled` 且没有可下载 job log；同 ref 重复手动 run `44387266332` 后被取消。结合 workflow 的 `cancel-in-progress: true` 同 ref 并发配置，这次重叠触发使修复验证没有产出可用矩阵。之后只能触发一个 run 并等待它自然结束，不重复 dispatch 或 rerun。
- 无同 ref 运行后仅手动 dispatch 一次完整双语 run `44388876849`（commit 仍为上述工具修复 SHA）；英文 job 已完成隔离容器和 OpenWrt 依赖安装，现于 `Install Playwright and find Chrome` 运行，中文 job 排队。此 step 已运行约 5 分钟且 job log 仅在完成后开放；未判门禁通过，也不再对此 ref 创建第二个并发 run。终态后需检查英文／中文截图 artifact 和 selected-mode 矩阵；若依赖安装重试或工具安装超时，按日志继续修复。
- 旧 run `44379124801` 的英文 job已失败，但中文 job仍在依赖安装步骤运行，因此 GitHub 尚不提供失败 job日志；该 run仍为进行中。待终态／可取日志时据实诊断，不能将未完成或取消的中文矩阵计作 PASS。


### CFI 来源管理 CRUD 持久视觉证据补齐（2026-11-19）

- 将 `a092ec2bb3d04d8817ebd480e40f944c35f4cbf4` 的来源管理 CRUD 从交互记录补齐为可审阅的 PNG 证据：空状态、添加对话框（桌面／320×568）、必填验证及原生 LuCI 错误提示、手动来源保存／重载、HTTPS URL 编辑／重载、待删除态与恢复空状态，以及新建 320×568 页面下的数据行。13 张截图均写入 `luci-four-repo-ui-evidence-2026-11-15/cfi-source-crud-evidence-2026-11-19/`，README 说明精确源码、测试环境、流程、视觉范围和设备安全边界；`SHA256SUMS` 已对每张 PNG 校验通过。两张经桌面改变 viewport 的诊断截图和一张重复桌面截图已排除。
- 验收动作只在独立 OpenWrt 24.10.8 临时实例执行；未抓取 `example.invalid` URL、未启用／启动 CFI。最终复核 `cf_ip.main.enabled=0`、服务 inactive、`uci changes cf_ip` 为空且无自定义 source section 后，已移除临时实例。此证据补足该页面的 CRUD 交互状态，不替代剩余视图、主题、语言、断点矩阵及四仓最终验收。


### UPnP Gate 修复分支活动运行更新（2026-11-19 20:42 UTC）

- 对 run `44388876849` 的活动 job 进行实时核验：英文 job 已通过 OpenWrt/LuCI、Playwright 与 checksum-pinned Aurora 安装，当前执行 `Capture all views and viewport/theme states`；中文 job 仍 queued。矩阵步骤于 20:34 UTC 开始，workflow 单 job 超时为 90 分钟，采集尚未终结，暂无截图 artifact，也没有可判断的 PASS/FAIL 结果。此为确认活动中的门禁等待，不启动重复 run。


### 整体进度估算更新（2026-11-19）

- CFI 来源管理 CRUD 的隔离实机流程与持久截图证据已补齐，四仓仍未完成的主要工作集中于 UPnP 当前双语矩阵/向导态复核、Nginx ACME 成功场景及四仓其余交互状态，之后还需同一候选包集合的最终联合构建/装机验收。基于阶段范围与剩余业务状态重新估算，整体约 **73% 完成 / 27% 未完成**；这是工作量估算，并非矩阵行数比例。UPnP run `44388876849` 当下仍活动中，不能按通过计数。


### 继续执行：Nginx HTTP-01 修复与 UPnP 精确英文门禁（2026-11-19）

- **Nginx ACME HTTP-01 缺陷已修复并取得真实挑战通过证据。** `acme.sh --webroot /var/run/acme/challenge` 将 token 写入 `.well-known/acme-challenge/`；五处生成配置此前都把别名指向 challenge 根目录，导致 Pebble 实际请求 HTTP-01 路径时返回 404。修正静态站点、反代站点、重定向站点及临时签发服务的 alias，包 release 升至 `1.8.11-r23`。隔离 OpenWrt 24.10.8 上 `PEBBLE_VA_ALWAYS_VALID` 未设置；Pebble 先复现旧配置授权失败，后从 Nginx 实例实际取到挑战并将授权置为 `VALID`。LuCI ACME 状态成功，证书 `http01.ui-gate.example.test` 显示 `valid`（捕获时剩余 89 天，自动续期关闭）；`nginx -t -c /etc/nginx/uci.conf` 成功。提交 `8cfff37` 已推送至 `codex/luci-ui-audit-20261115`。候选包 PR Build run `44402485969` 与 exact-source 英文 Real LuCI Gate `44402497029` 已触发，待 Actions 产物、双语截图审阅和主设备安装验证。
- **Nginx ACME 状态截图矩阵已完成并修正报告元数据。** exact candidate 文件 SHA 绑定到 `8cfff37`；中英文各 216/216 PASS、合计 432 视口×主题×语言行，0 browser errors，常用宽度、列举断点邻值和 320×568/568×320 短屏均无页面横溢。人工复核 Aurora Dark 中英文桌面和 320px 手机截图，证书状态、行内操作换行与页脚完整。此前本地自动报告仍沿用旧轮次的 `VA_ALWAYS_VALID` 描述，已更正成真实挑战场景并增加验证结果字段；`runtime-validation.txt` 记录 Pebble 授权与 nginx 配置检查（挑战 token 不入档）。证据与 SHA 校验索引：`luci-four-repo-ui-evidence-2026-11-15/nginx-acme-pebble-success-2026-11-19/`。
- **UPnP exact UI 英文门禁完成并人工复核向导模式选择。** run `44388876849` 的 EN job `135100784874` 已成功，报告绑定工作流提交 `80b271f86b549de42f9ce373f38781a9109b638f`；package/UI 源码与 `a065bce0d7c9db2623c067e7a8abae0bade69da4` 相同。全视图矩阵 1,686/1,686 PASS、wizard Safe/Auto 选择矩阵 420/420 PASS，均零 errors。对六主题分别生成并人工审阅全部 35 个视口的 Safe/Auto 配对联系表；同时新增六主题×8 个独立路由与根别名共 54 张完整断点联系表，逐表复核 1,686 行双向截图；未发现插件自有裁切、按钮重叠或异常横向滚动。另核对 Aurora Dark 320×568 与 568×320 原图，模式选中态明确，窄屏按钮堆叠、横屏步骤内容和操作可读。报告、原图、联系表与 SHA 校验索引位于 `luci-four-repo-ui-evidence-2026-11-15/upnp-run-44388876849-en-final/`，artifact ID `14469919162`，digest `sha256:d69509ab087e0071cd03d8eee3f21e34fdcb059641a1ffdce04270a18417122e`。该 run 的 ZH job仍在 `Install LuCI runtime and declared package dependencies`；在其终态及中文 artifact 人工复核前，不关闭 UPnP 双语精确门禁。

### Goal 继续执行：Nginx 候选预检与 UPnP 中文门禁重跑（2026-11-18）

- Nginx 候选精确源码 `8cfff372532ca642c23aa705f973351a449c97e9` 的 APK/IPK build run `44402485969` 与英文 Real LuCI Gate `44402497029` 均已确认仍为活动状态；分别在 OpenWrt package build 和 `Capture view and viewport matrix` 步骤运行。当前没有将未终结 job 计为通过。完成后需下载、校验精确产物与截图，再继续设备验证。
- UPnP run `44388876849` 的失败 run attempt 1 不能证明中文门禁完成；单独重跑失败 job 后，run attempt 2 的中文 job `135155843256` 已越过依赖安装步骤，进入 Playwright/Chrome 安装，尚未产出 artifact。等待该 job 终态并检查中文全视图与 wizard Safe/Auto 报告、截图及人工视觉审阅。
- 主路由只读安装前检查确认 OpenWrt `25.12.5 r33051-f5dae5ece4` x86/64，现有 `luci-app-nginx-manager 1.8.11-r22`、Nginx 正常运行、Nginx 配置测试成功、管理服务 enabled、`uci changes nginx_manager` 为空。当前配置文件未导出，未更改设备。版本与关键文件 SHA-256 基线见 `luci-four-repo-ui-evidence-2026-11-15/nginx-main-router-upgrade-2026-11-18/preinstall-baseline.txt`。收到精确 `r23` APK 后，须在设备升级前备份受安装脚本影响的 LuCI/Nginx Manager 配置与托管站点片段，并记录回滚路径；升级后逐项比较基线、确认 Nginx 服务与配置有效并核实目标文件属于 `r23`。

### Goal 继续：Nginx 英文矩阵人工审阅及主路由升级备份（2026-11-19）

- 从 exact-source English Gate `44402497029` 抽查到的完整 `report.json` 绑定源码 `8cfff372532ca642c23aa705f973351a449c97e9`，1,734/1,734 行 PASS、0 browser errors、0 页面横向溢出；六主题、34 个宽度和 320×568 / 568×320 短视口，含 8 个独立视图及 1280px root alias。报告全部 screenshot 引用均可定位。
- 完成 54 张主题×页面联系表的人工审阅（六主题各含八视图与 root alias）；包括此前已审阅的 Overview、Sites、Site Edit、Certificates、Files、Core Config、Backups，以及本轮复核的六套 Logs 与六套 root alias。未发现插件自有裁切、重叠或手机宽度操作布局不可用。完整审阅范围、视觉结论、不能由初始态矩阵证明的业务流程和整包 SHA256SUMS 已记录于 `luci-four-repo-ui-evidence-2026-11-15/nginx-run-44402497029-en/`。
- 对主 OpenWrt `192.168.2.1` 进行安装前复核：设备仍为 OpenWrt 25.12.5 x86/64，已安装 Nginx Manager r22；服务启用，`nginx -t -c /etc/nginx/uci.conf` 通过，Nginx Manager UCI 无未提交更改。创建设备本地 mode-0600 回滚包 `/root/nginx-manager-pre-r23-20261119.tar.gz`，SHA-256 `c1d66707039c53b783e997cafbb4da571be0a9e931eb83f11a96f4edc9816355`，覆盖 LuCI/Nginx Manager 配置、`uci.conf.template` 和插件托管配置目录；配置内容和私钥没有复制到工作区。状态与备份记录位于 `luci-four-repo-ui-evidence-2026-11-15/nginx-main-router-upgrade-2026-11-18/`。
- 已对精确相同 `8cfff37` 单独 dispatch Nginx 简体中文门禁 run `44407616647`；当前运行中，必须等终态、下载中文截图并完成人工审阅后才可安装 r23。
- UPnP run `44388876849` 的英文 job保持成功；中文 job `135155843256` 已通过 Playwright/Chrome 和 Aurora 安装，目前采集全视图与主题断点矩阵中。等待同一 run 自然终结，尚不计 PASS。
- **新增人工视觉问题：Nginx 文件页 14 项手机列表仍不够友好。** 全尺寸 320px Aurora Dark 原图确认每个条目均重复字段标签、修改时间多行折叠、操作按钮竖向堆叠；自动几何检查虽然 PASS，但人工视觉质量暂判 FAIL。已把问题、需保留的信息与重测范围记入 Nginx 英文矩阵审阅记录。待当前中文 Actions 结束后，需仅针对插件自有文件列表做紧凑移动呈现，再重跑英中精确矩阵和六主题宽度视觉审阅；不把这项误归为主题自身错误。
- Nginx Files 手机布局已按上述发现修正为 r24 候选（本地提交 `4887e15`，尚未推送）：保留 LuCI/主题原生表面与桌面表格；手机端把名称、元数据和操作收进紧凑条目，隐藏重复类型列和父目录无意义的占位值，按钮紧凑换行；保留权限、尺寸、修改时间和全部原操作。CSS 只限定 `.nm-file-table`，颜色、边框由主题决定。截图门禁增加 14 行 fixture、网格布局、类型冗余隐藏及操作组不溢出的断言。JS `node --check` 和 `git diff --check` 已过；待当前 r23 中文门禁自然完成后推送 r24，一次性构建并重跑英语/中文矩阵。


### 继续执行：UPnP 中文矩阵审阅完成与 Nginx r24 推进（2026-11-19）

- UPnP 中文 job `135155843256` 在 run `44388876849` attempt 2 成功结束；全视图矩阵 1,686/1,686 PASS，Safe/Auto 选择态 420/420 PASS，零浏览器错误，六主题全视图及根别名均有对应截图。UI/package 变更源码候选为 `a065bce0d7c9db2623c067e7a8abae0bade69da4`，工作流 SHA `80b271f86b549de42f9ce373f38781a9109b638f`。
- 已人工检查 54 张中英文路线×主题全断点联系表，以及六张中文 Safe/Auto 35 视口配对表；代表性短屏与横屏截图确认选择态、步骤区和页脚可读。未发现插件自身裁切、重叠或横向溢出。审阅结论、范围限制和 2,289 文件校验索引位于 `luci-four-repo-ui-evidence-2026-11-15/upnp-run-44388876849-zh-attempt-2/`；SHA256SUMS 已逐文件验证。向导步骤跳转/最终提交、真实服务与映射状态等尚未覆盖，仍需完成。
- Nginx r23 简体中文精确截图门禁 `44407616647`（SHA `8cfff372532ca642c23aa705f973351a449c97e9`）已完成，等待读取/审阅其中文报告和截图。由于 r23 英文文件页出现人工视觉 FAIL，r23 不作为最终安装候选；r24 定向文件列表布局修正 `4887e15` 继续进入双语/六主题断点复核。
- 为压缩步骤，只对 Nginx 改动命中的文件列表路由重做全断点视觉检查，并复用其它未受影响视图在精确 r23/r24 来源上已审核的证据；上游 run/artifact 源码、报告和截图仍逐项绑定，避免把旧提交结果冒充新候选验证。


### Nginx r23 中文精确矩阵复核与 r24 Actions 启动（2026-11-19）

- r23 中文 run `44407616647` / job `135166944869` 已成功，精确 SHA `8cfff372532ca642c23aa705f973351a449c97e9`，1,734/1,734 自动矩阵 PASS、零浏览器错误。报告、原始截图、六主题各 36 视口 Files 联系表与逐文件校验清单已保存于 `luci-four-repo-ui-evidence-2026-11-15/nginx-run-44407616647-zh/`，SHA256SUMS 3,669 文件通过。
- 文件页人工复核确认与 r23 英文相同的插件自有窄屏问题：14 项列表重复标签、修改时间换行并使操作纵向堆叠，视觉质量不通过，r23 不安装。该归因是插件选用窄屏原生表格堆叠的呈现逻辑，非主题本身故障。
- r24 `4887e15d686323e8d64c95a291c2b623fa7164f8` 已推送；GitHub PR Build `44412417010` 与英文 Real LuCI UI Gate `44412417081` 各启动一次，当前均运行中。待构建成功并完成 EN 全矩阵后，启动同一 exact SHA 的 ZH gate；重点重审仅受影响的 Files 视图，其他未变页面复用精确 r23 全路由审阅记录。r24 尚未生成最终候选 APK，未安装到路由器。


### UPnP 隔离容器入口复用探测（2026-11-19）

- 复用已存在的 `upnp-wizard-live-ui-20261118` 容器检查向导交互入口。容器已含 UPnP r14 候选，但经 `127.0.0.1:18088` 与容器地址访问 LuCI 均返回 `ERR_EMPTY_RESPONSE`／空响应；不能据此做浏览器交互验收，也没有把本轮列为通过。
- 为诊断临时调整隔离容器 uhttpd RFC1918 过滤后仍未恢复入口。已将 `/etc/config/uhttpd` 精确还原为镜像原件，SHA-256 与原镜像同为 `cb388ef8999d8b0faaf76ed22e68857f1d703822bae564e5157d9f9fb1b41ad3`，并停止容器；不影响主路由、插件配置或候选源代码。后续转用可工作的隔离 UI 入口完成 UPnP 交互状态。


### Nginx r24 中文运行中与英文文件页人工发现（2026-11-19）

- r24 exact source `4887e15d686323e8d64c95a291c2b623fa7164f8` 的 PR Build `44412417010` 和英文 Real LuCI UI Gate `44412417081` 均成功。x86_64 OpenWrt 25.12.0 APK SHA-256：`a4cb3491f6fa537334451dd98d537da59f321c553af6b99ef56b8a87eacf805e`；UI 报告 1,734/1,734 PASS、零浏览器错误。构建/矩阵 artifact ID、SHA、下载内容索引与 contact sheets 记入 `luci-four-repo-ui-evidence-2026-11-15/nginx-r24-en/`，1,838 个证据文件校验通过。
- 人工六主题复核 Files 320px 页面后发现 r24 仍有一个断行缺陷：Bootstrap 派生主题的 `uci.conf` / `uci.conf.template` 四按钮操作行会让“Actions”标签断成两行。自动几何断言未覆盖该文本断行，故 r24 的 Files 手机页仍为视觉 FAIL，不能安装为最终包。
- 修复已在本地提交 `201bb42`：清除插件动作标签继承的浮动、保持标签整行不可拆，并在视觉门禁验证伪元素的 computed float/white-space；包升至 r25，CSS 缓存键递增。仅改动手机文件页，不影响其它路由。r24 中文 run `44416078773` 尚在采集；结束前不会推送 r25，避免同 ref 并发取消。
- 既有复用策略不减验收范围：r25 重新执行中英文 1,734 行精确矩阵，人工关注六主题 Files 路由、断点邻值和短屏；其余路由按未受影响的精确来源文件与已有审阅证据对账。


### Nginx r25 隔离验证分支并行启动（2026-11-19）

- 为不取消仍在运行的 r24 中文门禁 `44416078773`，将本地 r25 commit `201bb42` 推到独立分支 `codex/nginx-r25-action-label-20261119`；Real LuCI 与 PR Build 的并发组按 ref 隔离，未改动 r24 原分支。
- r25 PR Build `44417838869` 与英文 Real LuCI Gate `44417838975` 已各启动一次，SHA 为 `201bb42`。待其完成后等 r24 中文 run 自然收尾，并在 r25 英文结束后触发 r25 中文门禁。


### Nginx r24 中文矩阵与人工复核收尾（2026-11-19）

- r24 中文 run `44416078773` 已成功，source SHA `4887e15d686323e8d64c95a291c2b623fa7164f8`，1,734/1,734 PASS、零浏览器错误，artifact `14481176451`；报告、原图、六主题 Files 36 视口联系表、review 记录及 SHA256SUMS（1,838 文件）已归档到 `luci-four-repo-ui-evidence-2026-11-15/nginx-r24-zh/`。
- 中文 320px 六主题人工审阅进一步复现“操作”标签在 Aurora Dark/Light 逐字竖排；其它 Bootstrap 系主题仍横向。结合英文四按钮 `Actions` 折行，判定为插件自有伪元素浮动与表格卡片布局冲突。r24 自动通过但人工不通过，不部署。
- 继续验证 r25 分支 `codex/nginx-r25-action-label-20261119`，run `44417838869` PR Build 与 `44417838975` English UI Gate 均已启动，SHA `201bb42b033b700013106c58c0ff2fcacb803cab`；状态在 run 自然终止前不登记通过。


### Nginx r25 人工失败、r26 可见性修正及门禁并行（2026-11-19）

- r25 英文全矩阵 1,734/1,734 自动 PASS、零浏览器错误；216 Files 行的 72 个手机主题/断点断言均通过。但人工审阅六主题 320px 文件页发现 Bootstrap Dark 的四操作按钮行把 `Actions` 截成 `Acti…`，r25 仍为视觉 FAIL。报告、全部截图、六主题 Files 联系表、审阅和校验归档于 `luci-four-repo-ui-evidence-2026-11-15/nginx-r25-en/`，1,838 文件校验通过。
- r25 中文门禁 `44421137931` 在发现 EN 手工 FAIL 后、截图采集期间被主动取消；保留所有已成功 exact-source EN 和 r24 ZH 证据。因最终包需要双语完整审阅，改由 r26 完整双语门禁取代重复的 r25 矩阵。
- r26 `ca5b189c56dcb244f734e4e637a9f59218e6df7a` 在 CSS 移动标签中增加 `width:auto`、移除 `max-width`、允许可见溢出并禁用省略，同时把这些 computed-style 条件加入断言；版本为 r26，cache-buster 递增。r26 通过独立分支 `codex/nginx-r26-action-label-20261119` 启动 PR Build `44421686827` 与英文 Real LuCI UI Gate `44421684310`；待它们自然完成再启动中文门禁。


### Nginx r26 候选构建完成，英文门禁采集（2026-11-19）

- r26 PR Build run `44421686827` 已成功，exact SHA `ca5b189c56dcb244f734e4e637a9f59218e6df7a`，OpenWrt 25.12.0 APK `luci-app-nginx-manager-1.8.11-r26.apk` SHA-256 `b7c327289e6a6ae7e1aa63339afa5a86674d747c95da65d861f6c76aebc30cc6`，artifact ID `14482972323`。产物/manifest 记录位于 `luci-four-repo-ui-evidence-2026-11-15/nginx-r26-build/`。
- exact-source 英文 Real LuCI UI Gate `44421684310` 仍在 Capture view and viewport matrix。该包尚未装入路由器；需待双语门禁、报告和 Files 手工截图复核后再决定。


### Goal 继续：Nginx r26 英文精确矩阵与手机文件页审阅（2026-11-19）

- r26 PR Build `44421686827` 成功，OpenWrt 25.12.0 APK SHA-256 `b7c327289e6a6ae7e1aa63339afa5a86674d747c95da65d861f6c76aebc30cc6`。exact-source EN UI Gate `44421684310` 已完成，SHA `ca5b189c56dcb244f734e4e637a9f59218e6df7a`，1,734/1,734 行 PASS、0 browser errors；报告含 8 routes × 6 themes × 34 widths，以及 320×568/568×320 短视口。
- 人工只复核此次有变化的 Files 页面：六主题各 12 个重点宽度（320–601，含 600/601 切换点）、两个短视口联系表，以及 320px 原始截图。六主题英文 `Actions` 标签完整可读；部分动作按钮换到下一行但无裁切或重叠，599/600 紧凑卡片布局与 601 原生表格布局切换正常。r26 英文改动范围视觉 PASS。报告、原图、六主题联系表及 SHA256SUMS 位于 `luci-four-repo-ui-evidence-2026-11-15/nginx-r26-en/`，1,839 个文件校验通过。
- 中文 exact-source gate `44424786657` 当前仍运行，尚未计 PASS；终结后按同一聚焦策略审阅 Files 视图，再决定候选安装。


### r26 主路由安装前重新核验（2026-11-19）

- 在等待 exact-source 中文门禁时，对主 OpenWrt 做了只读复核：仍安装 `luci-app-nginx-manager-1.8.11-r22`，Nginx 正常运行，`nginx -t -c /etc/nginx/uci.conf` 成功，`uci changes nginx_manager` 为空。
- `/etc/config/nginx_manager`、`/etc/config/luci`、`/etc/nginx/uci.conf.template` 与 Manager include 的 SHA-256 与安装前基线完全一致；设备根权限回滚包仍是 mode 0600、2,925 bytes，SHA-256 `c1d66707039c53b783e997cafbb4da571be0a9e931eb83f11a96f4edc9816355`。没有改动设备。
- r26 中文门禁 `44424786657` / job `135226698801` 仍活动于全视图与视口截图采集；当前尚无失败或终态，不重复触发。

### Nginx 主路由窄屏工具栏遮挡复核及 r27 修复（2026-11-19）

- r26 安装到主路由后，在 Aurora、中文、320×568 的 Files 页面发现主题自带的展开浮动工具栏盖住了插件自绘的路径输入框和操作按钮。回看 LuCI System 原生页时，同一个工具栏确实属于主题；按用户确定的归因规则，不改主题本身，只修插件 Files 自有视图在浮层展开时的窄屏避让。
- r27 `07c9459e53c2815acc4f5cf73033818f6b0aee55` 在 `nginx-manager.css` 给带有文件页工具栏的 `#view` 预留右侧空间，条件是窄屏且页面存在已展开的浮动工具栏；不按主题名称设置颜色、按钮外观或主题参数。`PKG_RELEASE` 提升到 27，CSS cache key 更新。
- 推送分支 `codex/nginx-r27-floating-toolbar-20261119`。PR Build `44429462606`、英文 Gate `44429463359` 正运行；中文 Gate `44429463720` 因同一 workflow/ref concurrency 规则自动取消，将在英文结束后顺序重跑，避免再互相取消。
- 当前设备截图仅在 CUA 会话中人工查看，尚无可归档 PNG；本项仍为待验证，不计 PASS。归档说明：`luci-four-repo-ui-evidence-2026-11-15/nginx-r27-floating-toolbar-20261119/README.md`。需在 r27 包安装后复看 Aurora 320px 展开状态并保存截图，再决定关闭。

### Nginx r27 实机反证及 r28 状态选择器修正（2026-11-19）

- r27 Build `44429462606` 两个 SDK 构建成功，EN Gate `44429463359` 成功。r27 APK `30bb946d9d24735f5675587cb866a7546c0ee2d420de15f94211defa3ea899c7` 已安装到主 OpenWrt；包升级后 Nginx 仍运行、配置测试通过，nginx_manager/luci UCI 均无待提交改动。
- 实机 Aurora 中文 320×568 展开工具栏后，路径栏和操作按钮仍被遮挡；折叠工具栏后相同内容没有覆盖。故 r27 对此项 **FAIL**。主路由视觉快照在 CUA 中复核，但尚未导出为 PNG，不能计入可归档截图门禁。
- 只读检查设备的 Aurora CSS 确认 `.floating-toolbar.collapsed` 是稳定的收起状态标记；r27 误依赖未实际触发的 `aria-expanded` 匹配。r28 source `c792306` 改为检查展开态容器类 `.floating-toolbar:not(.collapsed)`，不改主题资源或外观；Release/cache key 更新为 r28。
- r28 分支 `codex/nginx-r28-toolbar-clearance-20261119` 已推送；Build `44433047595`、英文 Gate `44433047758` 运行中。前轮中文 Gate `44429463720` 在 EN 同 workflow/ref 运行期间被 concurrency 取消；本轮将在英文终止后顺序运行中文，避免重复取消。
- r27 与 r28 详细证据索引在 `luci-four-repo-ui-evidence-2026-11-15/nginx-r27-floating-toolbar-20261119/README.md`。r28 仍需精确候选安装、实机展开状态审阅和截图后才能对此项判 PASS。

### Nginx 浮层安全区跨宽度修正及 r29 精确验证启动（2026-11-19）

- 按主题实际 CSS 核对，浮动工具栏在 `<48rem` 使用移动尺寸，且在 601–767px 仍存在；只在 `max-width:600px` 生效的 r28 不覆盖全部相关视口。未等待 r28 构建/截图矩阵完成，主动取消 Build `44433047595` 和 EN Gate `44433047758`，避免对已知不完整的断点范围继续消耗 CI。
- r29 source `5166fb15c3569cc44ad9e2f78401b41af6f87b4a` 将 Files 安全区规则从 600px 媒体查询移到全宽度，仅在 Files 页且主题浮动栏展开时生效；不修改浮动栏或其他主题外观。`PKG_RELEASE` 为 29，cache key 递增。
- r29 分支 `codex/nginx-r29-floating-toolbar-20261119`；PR Build `44435450315` 和 EN Real LuCI UI Gate `44435448599` 已触发。待 EN 完成后顺序触发 ZH。上一轮 r27 设备反证已记录，不能计 PASS。
- 本轮已完成的 Aurora 窄屏 r27 观察仍只在 CUA 中，尚未写出 PNG；r29 安装后必须保存至少 320×568 与 601/768 边界相关的可归档截图，人工确认展开/收起状态，以及桌面最宽视口安全区，再关闭此项。

- 过程压缩：对 r29 只检查改动覆盖的 Files 视图；复用已有英文 8 routes × 6 themes × 34 widths 门禁和 r29 精确源 Build，不重复跑未修改页面。追加中文矩阵是为了检查窄屏中文标签/换行。
- r29 EN Gate `44435448599` exact SHA `5166fb15c3569cc44ad9e2f78401b41af6f87b4a` 成功，1,734 行、0 浏览器错误；APK/IPK 构建成功。包已归档：APK SHA-256 `78505ca81296cc1e9144327892cb903bf09dfdf2b98c1240541c1448a38a3b56`，IPK SHA-256 `58c8f687d93fc6edb3e9d4a7f6deae573cd5ca8ae2ffe61e5bbc5d40b259480f`。
- EN Aurora 320px 全页截图与实际 Aurora 中文 320px 截图均确认浮动按钮会覆盖文件路径输入框；实机 768px 截图没有浮层压表格，CI 768px 全页截图中的横向主题导航覆盖是 fixed-position 全页捕获伪影，不作为产品缺陷或扩大 CSS 范围的理由。当前真实修复仍需等中文门禁成功后安装 r29，在设备窄屏验证。
- r29 中文 Gate `44438367207` 正在采集 1,734 行矩阵，当前尚无终态；不重复启动或取消。APK/IPK 和英文截图位于 `luci-four-repo-ui-evidence-2026-11-15/nginx-r29-toolbar-clearance-20261119/`。

### r29 实机发现级联覆盖、r30 优先级修正（2026-11-19）

- r29 中文门禁 `44438367207` 已成功：1,734 rows、34 widths、8 routes、0 errors，SHA `5166fb15c3569cc44ad9e2f78401b41af6f87b4a`。English/Chinese matrices与精确包均已完成，但并不代表已修复实机问题。
- r29 APK 安装在主路由用于候选核验，实机 Aurora 中文 320×568 再次证实遮挡。通过浏览器计算样式定位：主题 `#maincontent #view` 有两个 ID 的选择器优先级，覆盖了 r29 的 `body:has(...) #view:has(...)`；最终 padding-inline-end 仍是 0。r29 标记 FAIL。安装前后 UCI/配置哈希一致，Nginx 运行及 `nginx -t` 均正常。
- r30 commit `fd1a2cc4943e5b4b4558252523508374f0da36f7` 在同一避让规则加入 `#maincontent` 提升级联优先级，PKG_RELEASE/cache key 更新；已推送同一候选分支。PR Build `44441854439` 和 EN Gate `44441854142` 正运行。EN 自然完成后顺序触发 ZH，随后安装 r30 验证 computed padding、展开/收起和受影响边界。

### Nginx r30 实机通过，浮动工具栏避让完成（2026-11-19）

- r30 commit `fd1a2cc4943e5b4b4558252523508374f0da36f7` 双语 exact-source Real LuCI Gate 均通过：EN `44441854142`、ZH `44444652477`；各 1,734/1,734 rows、34 widths、8 routes、0 browser errors。PR Build `44441854439` 的 24.10.5 IPK 与 25.12.0 APK 均成功。SHA-256：APK `17ca33d9ee63c9e67ca72ff02228dde4e2d7c37e9a3fc80d6a1b6112ce599da0`；IPK `6283e7104bdf718490cc394149120f4dad15b4852f6400609a06b6573ae4ff69`。
- 主 OpenWrt 已从已知失败 r29 升至 exact APK r30。Aurora 中文实机在 320、600、601、767、768、1319、1320、1920px 且浮动栏展开时，`#view` computed `padding-inline-end=56px`；收起后为 `0px`。320px 路径框及动作按钮视觉上清晰避让。边界页表布局在 600/601、767/768 正常切换，桌面最宽处未出现内容遮挡。
- 安装前后 `/etc/config/nginx_manager`、`/etc/config/luci`、`/etc/nginx/uci.conf.template` 的哈希保持一致；Nginx 运行、配置测试通过，UCI pending changes 为空。浏览器临时视口已 reset。
- 英文/中文全矩阵报告、截图、联系表、APK/IPK、审阅记录与 SHA256SUMS 归档至 `luci-four-repo-ui-evidence-2026-11-15/nginx-r30-toolbar-clearance-20261119/`；3,678 个归档文件校验通过。此前 r29 记录为失败，不计入完成。

### 后续执行方式压缩（2026-11-19）

- 按用户要求减少重复但不降低验收覆盖：每项以精确源码 SHA、既有行级截图台账和验证结果为准；先查现有证据与候选差异，只补未通过或未覆盖的状态，不重跑未受影响的页面／主题／断点矩阵。共用 CSS、渲染器、门禁夹具或影响多个页面的改动，才扩展到所有受影响消费者。
- 新缺陷先以一次定向实测定位 DOM／计算样式／实际请求或后端结果，再实施修复；复测按改动影响范围选取最小必要门禁。最终候选阶段再完成四仓精确包构建、同机共存、配置／服务恢复和完整交付证据核对。
- 不重复 UPnP run `44388876849` 的双语视觉矩阵：EN 与 ZH 1,686 行及 Safe/Auto 选择态 420 行、人工审阅和 2,289 文件校验已在上文归档。其尚缺的是向导步骤跳转／最终提交、真实服务与映射等业务状态，而非默认视觉矩阵。

### UPnP 向导逐步交互与流程门禁（2026-11-19）

- 按既有矩阵以外的缺口补充向导十步状态和隔离环境 Safe Save，不重跑 UPnP 默认页面矩阵。英语定向 run `44452304777` 的报告显示 2,100/2,100 截图行 PASS、零行错误；安全保存读回成功且服务保持 disabled。该 run 整体红灯只由测试脚本错误地要求必须调用 fixture 造成，实际上使用的是只读网络检查 RPC。随后在 `2b61f70458ac691f955f7073704ea9ba37b6bb9f` 移除错误断言并保留真实只读 RPC。
- 英文截图、十步×六主题×35 视口联系表、报告及逐文件 SHA256 索引归档于 `luci-app-upnp-nat-relay/real-luci-ui-evidence-2026-11-15/upnp-wizard-flow-run-44452304777/`；2,283 项哈希已核对通过。抽查窄屏、中间宽度及桌面联系表，截图覆盖步骤导航、错误/提示、预览和安全保存后的结果。
- 修正后的简体中文定向 run `44456663142` 绑定 UI/package source SHA `2b61f70458ac691f955f7073704ea9ba37b6bb9f` 并成功：2,100/2,100 行、六主题、十步、35 个视口变体，零自动化错误及横向溢出；隔离环境 Safe Save PASS、配置读回一致且 `enabled=0`。自动与服务启动变更依照隔离容器安全范围未执行。
- 中文 2,222 个 CI 文件与 60 张主题×步骤联系表已归档至 `luci-app-upnp-nat-relay/real-luci-ui-evidence-2026-11-15/upnp-wizard-flow-run-44456663142/`；含 artifact ID `14497829840`、digest `sha256:579102faaba1407ec3a0bc8214fb8c6abdd88c58256fbe675937048642fc5244`。新增说明与校验索引后共 2,284 个文件；2,283 项 SHA256 校验全通过。抽查 Aurora Dark 568×320、320×568 的步骤 4 实际视口以及横竖屏联系表，短视口按预期可滚动，前进／后退按钮可用；完整视觉矩阵零溢出。英语与中文两次安全保存均只写入 disposable CI 容器，路由器配置未动。
- 为压缩重复，同 SHA push 自动触发的全量双语默认矩阵 run `44456651194` 已取消；仅保留 wizard-flow 定向任务 `44456663142`。没有取消或重跑其他已有证据覆盖的矩阵。


### CFI 设置页范围校验与保存交互证据（2026-11-19）

- 对精确源码 `a092ec2bb3d04d8817ebd480e40f944c35f4cbf4` 补充隔离 OpenWrt LuCI 实机交互证据，未重跑全视图矩阵。设置页输入 101 时原生校验提示 1–100 且 UCI 值仍为 8；输入 9 后 Save & Apply 成功，UCI 回读为 9。截图、复现脚本和 SHA-256 清单在 `luci-app-cloudflare-ip/luci-four-repo-ui-evidence-2026-11-15/cfi-settings-save-evidence-2026-11-19/`，清单四项已逐项校验。
- 旧隔离容器 `/etc/cf_ip` 权限为 0777，导致产品安全校验拒绝应用；仅将该测试目录权限改为 0755 后重试通过，没有改源码。流程完成后将 `/etc/config/cf_ip` 字节级恢复为测试前内容，SHA-256 与备份一致；`uci changes` 为空，服务仍禁用。
- 该项只补足设置页的英文范围校验／保存交互，不替代其他页面状态、语言／主题／断点矩阵或最终四仓候选包联合验收。


### CFI 高级页范围校验与保存交互证据（2026-11-19）

- 对精确源码 `a092ec2bb3d04d8817ebd480e40f944c35f4cbf4`，在复用的隔离 OpenWrt 24.10.8 实例中补齐高级页独立表单验收：Probe Timeout 输入 31 时 LuCI 原生 1–30 校验拦截、UCI 仍为 5；输入 6 后 Save & Apply 成功并从 UCI 回读为 6。截图、复现脚本和四项 SHA-256 校验清单位于 `luci-app-cloudflare-ip/luci-four-repo-ui-evidence-2026-11-15/cfi-advanced-save-evidence-2026-11-19/`。
- 验收后将 CFI 配置字节级恢复为基线，SHA-256 `5ed5a0e6dd9b45aee0628a8efe6f898cf44988def69a21b153f35b0f7c082aa5` 一致，`uci changes` 为空且 `cf_ip.main.enabled=0`。期间仅在无效 UCI 查询键修正后重跑该定向表单流程；没有重跑其它页面、主题或断点矩阵。
- 该项补足 CFI 高级页英文校验／保存交互，不代表 CFI 及四仓库的其它业务状态和最终联合验收已完成。


### CFI 主路由代理依赖只读确认（2026-11-19）

- 使用用户已授权的 192.168.2.1 Edge 会话只读检查当前实机；LuCI 为 OpenWrt 25.12.5 / Aurora Dark。CFI 设置页将代理模式识别为 OpenClash，OpenClash 子页正常渲染配置表单和既有备份列表；未点击保存、恢复、删除或运行优选，也未读取／记录配置文件中的域名和路径值。
- CFI 子导航没有 PassWall 页；源码菜单仅在 `/etc/init.d/passwall` 可执行时显示该页。结合主设备当前可见导航，PassWall 实机分支不可用，暂不把“缺少依赖”说成“实际表单通过”。后续如需验证真实 PassWall 表单，应在隔离设备准备 PassWall 依赖；现有 UI fixture 只可证明其视觉／缺失分支，不能替代该集成状态。
- 本次是当前设备的只读状态核对，未导出敏感配置截图，也不替代截图矩阵或配置交互验收。


### 当前候选与 Actions 证据对账（2026-11-19）

以当前工作树、GitHub run API 和源树差异为准，历史段落中的“仍待构建／矩阵仍运行”只保留为当时记录，不作为当前待办。对四个当前 HEAD 做过一次按 SHA 查询：

- PM `0d4460fc6902701dd231cbad5eaab17b6ce6cdbf`：CI `44374094084`、Remote SDK build `44374094062` 与 Real LuCI Gate `44374132753` 成功；同 SHA 自动重复全矩阵 run 已取消。包源码与该 UI-only 门禁测试修正前保持一致。
- CFI `a092ec2bb3d04d8817ebd480e40f944c35f4cbf4`：CI `44303561008`、SDK `44303859857`、双语 Real LuCI Gate `44303598148`／`44311538731` 成功。设置页和高级页的英文边界／保存交互已分别补有隔离实机证据；主路由只读确认 OpenClash 页面可用，PassWall 页面因设备缺少对应 init 脚本而不可用。
- Nginx `fd1a2cc4943e5b4b4558252523508374f0da36f7`：PR Build `44441854439` 与双语 Gate `44441854142`／`44444652477` 成功；HTTP-01 修复提交 `8cfff37` 是当前候选祖先，后续 `r30` 修复不需要重复 ACME 矩阵。
- UPnP `2b61f70458ac691f955f7073704ea9ba37b6bb9f`：精确 UI Gate `44456663142` 成功。同当前 HEAD 对 Build and Release `44251020329` 的比较，`package/` 树无差异；因此复用 `0f57513243f7d341d46c82c5fe955a1cae1e2928` 上成功生成并已实机安装的 r14 APK / IPK 属于同一包源码，不再触发重复构建。

当前仍需逐项关闭的是阶段 3 的剩余业务态、不可用依赖的真实集成分支及最后的候选集合验收；成功的默认 UI 矩阵和这些 Actions 状态不等于交互验收全部完成。已确认未完成范围中包括 UPnP 实际服务／写入回退、CFI PassWall 可用分支，以及 PM 和各仓其余待测业务态。

### UPnP 隔离实机服务与映射状态补充（2026-11-19）

- 为补默认矩阵之外的实际运行态，在一次性 OpenWrt 24.10.8 容器中验证当前 UPnP 源码：确定性 `upnpc` 夹具返回两个映射，实际 LuCI → rpcd/ubus → procd 服务 → nft 链接受 TCP 映射、拒绝低端口映射，并生成只存在于该容器独立网络命名空间的 DNAT 规则。页面 Start / Stop / Start / Stop 状态转换成功；运行、停止、重启和有数据的映射表已截图，人工检查桌面、320×568 竖屏、568×320 横屏，无页面横向溢出。
- 本次运行时由精确 HEAD `2b61f70458ac691f955f7073704ea9ba37b6bb9f` 的源码部署助手准备；当前 `package/` 树与成功 build run `44251020329` 的 `0f57513243f7d341d46c82c5fe955a1cae1e2928` 一致。该隔离环境无法下载依赖，故没有声称在此容器安装 Actions IPK。映射来自假 IGD 夹具，不代表真实网关兼容性。
- 结束后容器配置与基线 SHA 一致、`enabled=0`、UCI 无待提交改动、服务停止、UPnP nft 表不存在；额外的临时 LuCI 入站 nft 规则已删除。一次性容器已销毁；主路由未修改。README、复现脚本、六张截图和 SHA256SUMS 位于 `luci-app-upnp-nat-relay/real-luci-ui-evidence-2026-11-15/upnp-service-runtime-2026-11-19/`，九项 SHA 校验全部通过。
- 仅补服务生命周期与映射数据状态；未重跑双语、主题、全断点矩阵。UPnP 真实网关交互仍未覆盖，四仓最终候选集合验收仍待做。

### 进度估算与下一缺口校验（2026-11-19）

- UPnP 隔离服务生命周期／映射态及可审阅证据已新增完成；未重复既有默认矩阵。按阶段工作量估算，整体约 **74% 完成 / 26% 未完成**（估算值，不是截图行数比例）。
- 为避免把缺依赖页面误算通过，复核了可复用的 CFI 隔离 OpenWrt 实例：PassWall init 脚本与配置均不存在，故该实例不能证明 PassWall 真实页面／集成。主路由也没有 PassWall 服务；当前确认状态仍是“真实 PassWall 分支待覆盖”，没有新增长矩阵运行。下一步需准备隔离环境的兼容 PassWall 依赖，或先推进其他不依赖该服务的缺口。


### CFI PassWall 实际依赖页面与保存暂存验证（2026-11-19）

- 在隔离 OpenWrt 24.10.8 上安装通过官方签名索引验证的 PassWall 26.11.11-r1，并补齐 LuCI 简体中文基础及 PassWall 翻译。对 CFI 精确源码 `a092ec2bb3d04d8817ebd480e40f944c35f4cbf4`，PassWall 页六主题模式、36 个断点宽度、两个短视口及入口别名：英文 234/234、中文 234/234 全通过，零自动化错误和横向溢出；中文校正后的全宽度联系表与短视口/别名联系表已人工审阅。没有重跑 CFI 其余页面的既有门禁。
- 真实 CBI 保存交互将测试值经页面 Save 暂存在 LuCI rpcd 会话，并读回两项值；未点击 Save & Apply。`cf_ip.main.enabled=0`，全局 UCI 无待提交项，配置文件哈希与测试前相同；PassWall 开机自启禁用。容器 `/etc/init.d/passwall running` 的探针返回成功但进程列表中没有 PassWall/代理进程，因此不把该探针或本次验证声称为真实代理服务运行/流量转发验证。
- 截图、矩阵报告、交互脚本、包校验值及文件清单：`luci-app-cloudflare-ip/luci-four-repo-ui-evidence-2026-11-15/cfi-passwall-runtime-2026-11-19/`。中文基础语言包缺失导致的早期英文按钮截图保留作诊断；最终报告使用已安装标准 locale 包的复跑结果。
- 在既有约 74% 的工作量估算上，本次关闭 CFI PassWall 的真实依赖页面与 Save 暂存缺口后，整体估算调整为约 **75% 完成 / 25% 未完成**。尚未完成真实 PassWall 代理运行验证、PM 和四仓其余交互/业务状态、最终四仓候选包联合构建与装机验收。此比例是阶段工作量估算，不是截图行数比例。
- CFI `487c9896cc2f9d066f52eceb811c7e02da0407c0` Overview 状态视觉复核：英文 run `44481199262`、中文 run `44483740315` 的默认态与代理已安装态各 234/234 PASS；各覆盖 36 宽度点、320×568／568×320 短视口、六主题模式与根入口别名，零浏览器错误、溢出或截断。源码差异确认 `a092ec2..487c989` 未修改 view/CSS/template，故只定向补受后端状态逻辑影响的 Overview。中英文四个场景的 24 张 contact sheets、全页图、报告和人工审阅记录位于 `luci-app-cloudflare-ip/luci-four-repo-ui-evidence-2026-11-15/cfi-overview-status-r20-2026-11-19/`；检查确认原 Bootstrap 320px 的状态未知标签截断已修正，中英文状态标签完整。英文 run `44481199262`／artifact `14509297183` digest `sha256:872f3fc350232c30a0f6088d44029f9de722d7b94e5992adfd1042550101d9a9`、中文 run `44483740315`／artifact `14510296861` digest `sha256:8bb0229ff1260391ea265df2749bc5a5845ef1534806e6dbd493c95e161eb98b` 的下载包 SHA 均核验匹配。SDK Build `44480757026` 与 CI `44480756928` 成功，artifact `14508418010` 内含 GUI `luci-app-cloudflare-ip-2.6.2-r20.apk`（SHA-256 `ad3b68187d1f29ee522821791f14025283f9542c539be5bac802898286ac3acb`）和兼容包 `luci-app-cloudflare-ip-rill-2.6.2-r20.apk`（SHA-256 `87d9178fb29798d4a9f739fc794b8d6b808812ebf3459a5efcf3feefb10d7426`）。主 OpenWrt 25.12.5 x86/64 已从 Actions 候选安装 CFI 两包 r20/r20；PM `1.0.7-r1`、Nginx `1.8.11-r30`、UPnP `1.3.16-r14` 与共享 `rill-runtime-preview 1.5.6-r6` 均保持原候选，不重复安装。安装前模拟只列两项 CFI 升级；安装后 CFI 配置 SHA `2343cdf28313101c7832d4c333282042fb4ce76ee82d6faa44a6c76e9651361a`、`enabled=1`、UCI pending 为空、init `active with no instances` 及 runtime SHA 均与基线一致。设备 live Overview 显示 r20；新默认配置按 APK 约定另留 `.apk-new`，旧配置未覆盖。候选／回滚包、备份哈希和部署核验记录及 1,019 项文件清单均在上述 evidence 目录 `install-audit.md`／`SHA256SUMS`。下一步继续关闭 PM、UPnP、Nginx 的剩余交互／业务态和最终四仓证据审计。

### 精确证据复用与四仓包共存复核（2026-11-19）

- PM 受控基准测试 validated／unvalidated 结果态已有精确 UI 源码 `af877339d3a30ced664cc96101a0f43ebf47724c` 的双语 Real LuCI Gate run `44374132753`：英文、中文各 492/492 PASS，六主题、39 个宽度及两个短视口；12 张联系表和代表性窄屏／桌面图已人工审阅。记录在 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-run-44374132753-{en,zh}-result-review/`。结果态矩阵不再重复运行；它不替代真实 A/B 生命周期（已在上文 `06521c7` 隔离 OpenWrt 记录）或 health-only／passive-before-after 页面状态。
- CFI r20 安装后再次只读核对同一 OpenWrt 25.12.5 的包清单：PM All-in-One `1.0.7-r1`、CFI GUI／Rill compat `2.6.2-r20`、Nginx `1.8.11-r30`、UPnP `1.3.16-r14`、共享 `rill-runtime-preview 1.5.6-r6` 同时安装；Rill 二进制 SHA `c3ad43ed73cc7b57dbc3835ea01f8b6ff03d69ab213655b72c60e25f05f96abe`，`uci changes` 为空。既有四仓同机资源 SHA 与页面实视记录可复用，CFI r20 的精确包、资源 SHA 和配置备份由上方 install-audit 证明。该复核只更新共存状态，不替代仍缺的业务交互和最终逐项证据审计。
- 后续执行时先按页面／源码 SHA 对账再列剩余状态；已覆盖的业务矩阵、实机检查和构建产物直接复用，只补缺失范围。对不相关页面不重复生成截图；只有源码差异影响共用 CSS、渲染器或状态结构时才扩大回归范围。保留当前 PM 工作树未提交的 `tests/real-luci-ui-visual.cjs` 改动及未跟踪证据，不将它们纳入测试、构建或提交。

### UPnP 真实 IGD 隔离验证准备（2026-11-19）

- 为补既有 `upnpc` 确定性 fixture 不能证明真实 IGD 协议交互的缺口，尝试在独立 Docker 网络接入 `miniupnpd`。Debian APT 镜像连接超时；随后从主设备配置的软件源仅下载 `miniupnpd-nftables 2.3.9-r2`，但 `apk verify` 在主设备和隔离容器都返回 `UNTRUSTED signature`。未安装该包，也未用 `--allow-untrusted` 绕过校验，因此此项仍未通过。
- 已删除本轮自建 Docker 容器、网络及临时 APK；主设备仅短暂在 `/tmp` 存放下载包，结束时已删除；未触碰任何配置或服务。后续寻找可验证签名的包／源码构建路径，或先推进其它已可验证的业务态；不重复这条失败的 APT 下载路径。

### UPnP 标准 IGD 协议与插件端到端同步（2026-11-19）

- 接续上一条失败尝试，改为在隔离 OpenWrt 25.12.5 容器配置设备现有 `mirror.sjtu.edu.cn` repositories/key；`apk update` 成功验证 11,258 个索引包后，从签名仓安装 IGD `miniupnpd-nftables 2.3.9-r2` 和客户端 `miniupnpc 2.2.8-r1`，没有安装未受信任的裸 APK。
- 在独立 `10.77.43.0/24` Docker 网络，用真实 miniupnpd daemon 完成 SSDP 发现、根描述读取和 SOAP 状态查询；从另一个 OpenWrt 客户端通过 SOAP `AddPortMapping` 建立测试 TCP 映射，miniupnpd 在自己的容器命名空间建立对应 nft 规则。
- 当前插件 exact source `2b61f70458ac691f955f7073704ea9ba37b6bb9f` 的 `upnp-nat-relay --dry-run` 读到 1 项并接受 1、拒绝 0；随后 `--sync` 成功，客户端 `inet upnp_nat_relay prerouting` 出现预期 DNAT 规则。配置 `enabled=0`，未启动 relay daemon。清理时 `--clear` 成功、插件表消失；SOAP `DeletePortMapping` 返回 0；IGD 日志确认 DNAT/filter 映射移除；容器、network、临时 image/包和测试 nft 表均已清理。
- 证据 README、miniupnpd SOAP/规则日志与 SHA256SUMS 位于 `luci-app-upnp-nat-relay/real-luci-ui-evidence-2026-11-15/upnp-real-igd-interoperability-2026-11-19/`，校验通过。该项关闭标准 miniupnpd IGD 与插件真实发现／读取／同步／恢复链路缺口，不声称兼容每一种物理家用网关。截图矩阵和实际数据视觉证据继续复用既有记录，无需重跑。

### 主题包版本更新要求（2026-11-19）

- 用户要求后续主题视觉验收统一使用最新可获取的包，先前主题包结果不再作为最终验收依据；此前三种主题按设备安装清单确认是 Aurora、Bootstrap（含默认／Light／Dark 资源模式）和 Vantage。
- 设备只读包清单显示当前已装 Aurora `1.2.0-r20260808`、Bootstrap `26.218.70234~1654281`、Vantage `1.0.20-r1`；设备配置的软件源可升级 Aurora 至 `1.4.3-r20261104`、Bootstrap 至 `26.317.52279~1c75ea4`。官方 OpenWrt 25.12 feed 可见 Bootstrap `26.320.60423~5331286`；Vantage GitHub latest release 为 `v1.0.20`（2026-11-12）。后续以实际下载／安装并记录包 SHA 的最新兼容包为准。
- PM 2026-11-19 Benchmark health/passive 矩阵使用了过期 Aurora `1.4.0-r20260920`，已标为 superseded，仅作历史诊断，不计最终 theme gate。针对新包只补受主题资源影响的视觉矩阵与必要截图人工审阅；已有业务状态和源码不变的交互门禁不重跑。最新包与旧包资源哈希对账后，再决定页面覆盖范围并记录版本、来源与 SHA。

### PM 最新主题包完整视觉矩阵补验（2026-11-19）

- 已用最新兼容主题包在一次性 OpenWrt 25.12.5 x86/64 LuCI 候选中补齐 PM 最新主题视觉审阅：Aurora `1.4.3-r20261104`（SHA-256 `cbd8044c36c3cd475e2fc9c26433e8fc9440ba9fb469d181afa490ae1fa1a831`）、Bootstrap `26.320.60423~5331286`（`5e24f8ae17a855623800f1ab2f3b2d6d5dda6f2786fbca82942f8998cdec064d`）、Vantage `1.0.20-r1`（`7c231822403f5dd346ebe800e290054ca2e624cdfd29d58dc251edd74619c0a6`）。前两者源自签名仓库索引，Vantage 与 GitHub release 校验值一致。裸 APK 的 `apk verify` 返回 `UNTRUSTED signature`，故没有通过包管理器安装；矩阵只从精确归档提取其主题静态资源供真实 LuCI 加载，未执行包安装脚本，物理主路由未修改。
- 双语 × 8 种主题模式 × 8 个 PM 页面及适用状态，共 16 份报告、每份 410 行，合计 **6,560/6,560 PASS、0 失败、0 浏览器错误**。覆盖 39 个视口宽度（320–1920 px）、320×568 与 568×320 短视口，以及 Benchmark health-only、passive-before-after 两种状态。128 张页面联系表均完成人工视觉检查；没有发现 PM 自定义样式导致的裁切、重叠或断点异常。
- 严谨归因结果：Bootstrap Overview 的绿色状态横幅来自 LuCI 原生 `.cbi-section.alert-message.success`；320 px 处的 5 px 内部 tabmenu 滚动范围属于 LuCI 原生导航，页面没有横向溢出。Vantage 手机端底部导航由其 `vantage.css` 在 `max-width:720px` 将 `.vt-rail` 固定到底部并给 `.vt-frame` 留出空间。以上均为主题／LuCI 外壳行为，不改 PM CSS。
- 联系表、逐行截图、报告、运行日志、原 runner 副本、人工审阅和 SHA256SUMS 位于 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-benchmark-health-passive-2026-11-19/latest-package-full-matrix/`。之前 Aurora `1.4.0` 相关结果明确作废，不再用于最终验收。
- PM exact UI package build/install 的 GitHub Actions run `44363269348` 与主 OpenWrt 实装证据已在 `pm-final-install-9080122-2026-11-19/device-install-audit.md` 绑定同一 `af877339…` package subtree；此处复用该证据，不重复构建或重装。叠加本次最新主题包矩阵后，**阶段 1（PM 普通用户界面、双语与响应式主题复核、Actions 构建和设备安装）现为 PASS**，可继续阶段 3。主题 APK 因裸包签名不可验证而只在 disposable candidate 提取其静态资源，未声称通过 apk 安装。
- 候选 UCI 已恢复 Bootstrap (`mediaurlbase=/luci-static/bootstrap`, `theme=bootstrap`)、`lang=auto`，pending changes 为空；一次性候选容器已停止。整体按阶段工作量估算从约 **75% 调整为 77% 完成 / 23% 未完成**；主要未完成项仍是阶段 3 的四仓其余真实交互／业务状态、最终候选构建和联合装机逐项验收。该比例是工作量估算，不是截图行数比例。


### 最新主题包四仓实机矩阵与 CFI 移动表头修复（2026-11-19）

- 使用主 OpenWrt 上四个实际候选包及已升级主题 Aurora `1.4.3-r20261104`、Bootstrap `26.320.60423~5331286`、Vantage `1.0.20-r1`。Bootstrap 默认浅／深和 Aurora 浅／深双语矩阵完整：Nginx 每份 289/289 PASS；UPnP 每份 281/281 PASS；CFI 英文每份 267 行（229 PASS、38 PassWall N/A），中文每份 305 行（267 PASS、38 N/A），均无浏览器错误。Vantage UPnP 深色双语各 281/281 PASS；浅色中文一行模式初始化误报由修正后的每页原生切换专项验证替代，双语各 18/18 PASS。
- Vantage Nginx 自动报告对可访问的内部表格滚动产生 `mobile-table-overflow`；两种模式、双语每份 48 项均确认页面 `overflow=false`、scroll region 可访问、移动卡片布局启用，320px Sites/Certificates/Files 等截图人工复核内容完整，归为检测误报。Vantage CFI Sources 的窄屏根溢出来自主题对 LuCI 原生 CBI 描述行的不换行表现，属主题自身，不增加插件补丁。
- Vantage CFI OpenClash 两种短屏下发现主题通用 `.table > thead` 覆盖插件移动端表头隐藏规则。源 CSS 已提升为 `#maincontent .cfi-openclash-backup-table > thead`；在已安装 CFI `2.6.2-r20` 上临时叠加精确 CSS 文件，Vantage Light/Dark、双语、320–601px 的 12 个断点宽度、320×568／568×320 短视口及根别名均 30/30 PASS/语言；表头在 600px 隐藏、601px 显示。截图中的 OpenClash 文本输入已视觉遮盖，不记录配置值。
- 临时 CSS 验证后，设备原 CSS SHA 恢复为 `38867fe85829b69aac6d1710e838dea41e089f8a8a6e187318fa1af8ab4da579`；LuCI 配置字节级恢复为预检哈希 `82a92faf05f9bde20eb6a60dba227046e80b2de59408845d8a812ef05d7ba23e`、Aurora、`lang=auto`，无 UCI 待提交项。证据与报告在 `luci-four-repo-ui-evidence-2026-11-15/theme-latest-router-install-2026-11-19/`。
- 本地官方 SDK 下载因低速在 109 MiB、解包前终止，没有生成候选包。该 CFI CSS 改动仍未进入远端提交，因此 GitHub Actions 构建、精确 APK 安装及包级截图复验尚未完成；直接 CSS overlay 仅证明浏览器级规则有效，不代替这些必测项。没有创建提交或推送。Goal 保持 active。
- 四阶段/三阶段范围（PM、共享 Rill、四仓 32 视图）逐项状态、缺证据和下一步汇总见 `luci-four-repo-ui-evidence-2026-11-15/goal-completion-audit-2026-11-19.md`；该审计维持原始目标范围，不把浏览器 overlay 误算为 Actions 包级 PASS。

### CFI 精确 Actions 包绑定与四包设备状态快照（2026-11-19）

- CFI 当前 HEAD `9106a085a8ff2a9171c17c3834c3bc9bcd6d9bd0` 的 OpenWrt SDK build `44551549488` 成功；精确 UI APK `luci-app-cloudflare-ip-2.6.2-r20.apk` SHA-256 `eb2aca13d26e46b5b0753da50d200b16012ec2c1ec6abf3c002fa75ddfbf9745` 已重新安装到本地 OpenWrt。安装后 UI CSS SHA `c66b698e94f603631483210c73171e88fda6a8fac717d79e619e1a1fd849bbbb` 与当前源码一致；LuCI、CFI 和 PM 配置、共享 Rill 二进制哈希均未变化，UCI pending 为空。四仓候选和单一共享 Rill Runtime 共存状态见 `luci-four-repo-ui-evidence-2026-11-15/final-four-package-device-state-2026-11-19.txt`。
- Vantage OpenClash 移动端表头修复的既有精准 CSS overlay 矩阵为中英文各 30/30 PASS，包含 Light/Dark、12 个宽度、两个短视口和 root alias；本次 Actions 包 CSS 与矩阵修复 selector 一致。之后仅删除页脚 `margin-top: 2em`，用户明确豁免此项单独视觉检查。已将 exact APK 与四包候选哈希归档至 `luci-four-repo-ui-evidence-2026-11-15/four-repo-footer-candidates-2026-11-19/`；最新联合设备状态见 `final-four-package-device-state-2026-11-20.txt`。
- CFI CI run `44551549429` 的各代码、包和 runtime qualification job 均成功；仅 `evidence-manifest` aggregation 失败。对该单独 job 重跑仍因“exact-attempt artifact missing/expired”失败；不影响独立成功的 SDK 包构建，最终报告须保留这一 CI 证据聚合限制，不能称整个 CI 全绿。
- PM History null 节点修复已用 All-in-One `r2` 三架构 Actions 构建并安装，split UI `r12` 构建成功；隔离 OpenWrt 中的实际回滚交互、回读和前后截图通过。最终 PM Real LuCI UI Gate `44568695570` 的英文 job 已成功，中文 job 仍运行；待下载并人工复核最终双语报告与受影响页面截图。
- 以当前证据估算总体约 **90% 完成 / 10% 未完成**（按阶段工作量而非截图行数）。其余主要为 PM 最终双语 UI gate、受影响页面人工图审和最后逐项审计／校验；未完成前保持 Goal active。

### PM 阶段标签修复双语门禁与 Vantage 字段宽度补正（2026-11-19）

- PM Benchmark 阶段标签修复提交 `a8cc5a5e0db4f0ebb64eea0d23d72ef9c9e25f6f` 的精确源码双语 Real LuCI Gate `44574272144` 已成功：英文和中文各视觉矩阵 1,968/1,968、受控基准结果 492/492、Overview 断点邻值 36/36，报告均绑定 exact SHA，零浏览器错误。All-in-One r3 多架构 Actions run `44574272287`、split UI r13 `44574272224`、CI `44574272241` 均成功；r3 已安装于本地 OpenWrt，CSS SHA 与源码一致。英文／中文截图、报告、artifact digest 与人工审阅记录位于 PM `pm-benchmark-stage-wrap-2026-11-19/`。
- 人工切换主题比对了 Vantage 768px 的 PM Settings 原生 CBI 与 Benchmark 页面，确认设置表单控件宽而完整，Benchmark 因原生 CBI 字段嵌入双列插件 toolbar 后挤窄，属于插件布局组合问题。提交 `58c8bc7b52e0d89a3acad8cc82de18889fbda130` 在 601–900px 令标签位于选择控件上方并使控件填满自身单元格；没有覆盖主题控件颜色或表面。临时精确 CSS SHA `bf0142c77828e8a644eb530d2b1181176cda07a244e3675b598e1eac0d26e0fa` 的 Vantage Light/Dark × EN/ZH 定向报告各 27/27 PASS，涵盖 600/601/768/899/900/901/1024、短竖／横屏与 benchmark default、health-only、passive-before-after；Vantage 实机截图人工确认 768px 全选项文字可读。证据在 PM `pm-benchmark-stage-wrap-2026-11-19/vantage-toolbar-58c8bc7/`。
- 新源码的 r4/r14 包构建和双语全量 UI Gate 已由推送触发，run IDs：CI `44583783028`、split UI SDK `44583783064`、多架构 All-in-One `44583782853`、Real LuCI Gate `44583782875`。构建与 gate 完成后安装 exact r4、抽查最新包截图并刷新四包设备快照；其他页面复用不受本次 Benchmark CSS selector 影响的矩阵。

### CFI r21 Sources 修复收尾与最终交叉对账（2026-11-20）

- CFI Sources 表头溢出的主题归因修复 `9c38ca2fbc1048bc4db50399cce042a7432839be` 已由 SDK build `44614746019`、CI `44614746010` 和双语 exact-source real LuCI gates `44614929935`／`44616855548` 验证成功。UI APK SHA-256 `c39df9bc01130dbe914de01a22fcce4051bcb6e832948fe112f0b83165bf748a`、Rill glue r21 SHA-256 `3dc6ad3fe92ffa57837cfebabe1310e6ce47c5536fefc03ffba4d3336769d904`；两包均安装到本地 OpenWrt，`/usr/bin/rill-runtime` 与 CFI 配置哈希不变。
- 安装 exact r21 后，在最新 Aurora、Bootstrap、Vantage 主题包上重新运行 CFI Sources 页面：六个主题模式 × 中英文各 39 行 PASS，共 468/468；覆盖 36 个常用和断点邻值宽度、320×568／568×320 短视口及根入口别名，零页面横溢出和浏览器错误。针对修复点的专项报告还覆盖所有 38 个 Sources 视口宽度并记录隐藏表头的实际几何。手工检查全部 12 张 320px 截图及 Vantage 英文 Light/Dark 的 700/701px 边界图，记录于 `luci-app-cloudflare-ip/luci-four-repo-ui-evidence-2026-11-15/cfi-source-r21-package-2026-11-20/visual-review.md`。Vantage 固定导航和操作栏的覆盖归属已标明为主题自身。
- 已用 exact r21 更新四包同机快照：CFI UI/Rill glue r21、Nginx r30、PM r4、UPnP r15 和唯一共享 `rill-runtime-preview 1.5.6-r6` 共存；配置与服务状态保留、UCI pending 为空，LuCI 恢复 Aurora／lang=auto。快照 SHA-256 `80f6afcc9a492bf85bdf301ad311b1179c0c87ecc632b8a736e354f2817006f5`。CFI build/gate、包、截图和报告校验清单位于 `cfi-source-r21-package-2026-11-20/`。
- 本节更新覆盖此前记录的 CFI r21 build/install/theme-matrix pending 项。Goal 仍 active：需完成最后的四仓逐项视图／业务状态／主题语言断点证据对账、当前候选包关联、人工审阅与清单哈希核验，并处理任何仍未 PASS 或缺少依据的适用行；不能由本次 CFI Sources 修复验收推断全 Goal 已完成。

### 四仓交互证据绑定和历史门禁误报复核（2026-11-20）

- 已按 LuCI 多层审计技能逐项比较当前候选源码与 PM rollback、CFI settings/advanced/source CRUD/PassWall、Nginx site/certificate/backup、UPnP wizard/real IGD 的交互证据。具体到视图和选择器的差异说明见 `luci-four-repo-ui-evidence-2026-11-15/interaction-source-reconciliation-2026-11-20.md`。各旧交互报告的目标业务路径没有被之后的页面/后端修改改变；Nginx 备份创建与恢复另有 exact r30 设备包的直接交互截图。状态截图适用的主题包版本仍需最后盘点。
- 对 `route-coverage.csv` 的 289 行和 supersession CSV 作机器核验：原状态为 273 PASS、7 FAIL、8 PENDING、1 N/A；15 个失败／待补旧行均匹配到对应 route/state/viewport，新截图文件存在且 SHA-256 与表格一致，0 对账错误。
- 核对 Nginx 最新主题矩阵发现有效六主题 × 双语的 12 份报告共 3,468 行，截图完整。四份 Vantage 报告各有 48 条原始 `mobile-table-overflow` FAIL。逐条指标表明 page/document width 与 viewport 相同、无页面横溢；内部表格区域均可访问并支持键盘横向滚动。已人工打开 Vantage Light 320px Sites、Certificates、Files、Backups 图，卡片/行内动作可读可达。按 Goal 明确允许的可操作组件内部滚动标准逐行定为 PASS，原始报告保留不改。192 行 disposition、对应路径与图像哈希记录在 `nginx-vantage-scroll-flag-reconciliation-2026-11-20.csv`；r30 相比矩阵使用的 r29 源码只有用户豁免的 footer `margin-top: 2em` 删除。
- 更新中央 `goal-completion-audit-2026-11-19.md`；Goal 继续 active。下一步核验所有适用状态截图与最新主题包之间的绑定、剩余 review/checksum manifests 和未收录的视觉状态，然后再作完成判定。

### 交互态视觉覆盖缺口重新盘点（2026-11-20）

- 当前四仓普通路由矩阵已完成交叉清点：PM exact-source 最新主题双语报告 6,560/6,560 PASS；CFI 全页旧报告、r21 Sources 复测和 OpenClash/Overview 专项修正均有报告及截图；Nginx 与 UPnP 的有效六主题双语报告均列入集中索引。报告级索引和每份报告的截图引用完整性在 `luci-four-repo-ui-evidence-2026-11-15/final-cross-repository-matrix-index-2026-11-20.csv`。
- 不把一般路由的截图当成交互态的视觉替代。重新对照计划第 4 节“全覆盖”后，识别出 16 组尚缺最新主题包双语及相关宽度视觉证据的不同状态布局，具体截图范围、现有证据与源码适用关系在 `luci-four-repo-ui-evidence-2026-11-15/interaction-state-visual-coverage-gaps-2026-11-20.csv`。包括 PM 回滚、CFI 表单验证/来源 CRUD/运行态、Nginx 表单与备份/日志动作、UPnP 向导后续步骤/保存/诊断/真实映射。
- 因该项原属目标范围，修正先前 95% 估算为约 **90% 完成 / 10% 未完成**。接下来只补这 16 组状态的缺证据组合，复用已通过的默认页面矩阵，不重跑完整宽度矩阵；最终完成仍要求逐状态图像人工审阅、准确源码/包绑定及恢复检查。

### 继续执行：关闭 CFI Settings 条件字段主题视觉缺口（2026-11-20）

- 完成六主题模式 × 中英文 × 自定义计划／HTTPing 筛选 × 320×568/1280×900 的 48 张当前 r21 截图；12 份报告均零错误且截图引用完整，人工复核记录在 `luci-four-repo-ui-evidence-2026-11-15/cfi-settings-conditional-visual-2026-11-20/visual-review.md`。
- 通过设置页源码未变、条件字段为原生 CBI 控件且无专属样式，并引用 Settings 路由 38 视口行的全断点矩阵作为断点覆盖依据；Vantage 固定保存栏／帮助折叠已按设备安装 CSS 归因为主题原生行为。
- 更新交互缺口 CSV 的状态、中央矩阵索引（68 行）和 SHA256 清单。交互态 16 组中 1 组关闭、15 组仍待完成；按阶段工作量粗估约 91%。

### 后续检查发现的 CFI 英文目录错误（2026-11-20）

- 英文 Sources 错误态截图暴露 PO 语言错配；核对到 90 条英文目录中文译文，已在验证分支提交修复并提升 r22。Real LuCI 工作流现按选择语言编译/加载对应 LMO，也监听 PO 变更。
- 本地 PO、workflow lint 和脚本语法已通过；Actions build 与中文实时 UI 门禁在运行。英文门禁因两次 workflow_dispatch 并发导致首个运行被 workflow 自身取消；将在中文 run 完成后串行派发。
- r21 Sources/Logs 状态截图只能作为缺陷定位记录。r22 构建、双语 Actions gates、安装后最新主题复拍与人工审阅仍待完成；不更新完成比例，也不关闭对应状态缺口。

### CFI Sources / Logs 状态与主要断点补齐（2026-11-20）

- 在 Actions r22 包对应的 UI 源码 `74f8b8578889fc1fcdf221a9e2af03220292d074` 上，完成六种最新主题模式 × 中英文的 Sources/Logs 错误、未保存草稿刷新成功/失败及清日志确认视觉状态。12 份规范报告共引用 1,728 张截图，均零页面错误、截图缺失或状态断言失败；所有修改性 RPC 均由浏览器拦截或取消。
- 按用户最新要求以主要断点完成审阅。11 组组合已有 36 宽度补充截图；最后的 Vantage Dark 中文组合只补 320、420、600、700、768、900、1048、1100、1280、1319、1440、1920px 和两种短视口，没有为此重复全量宽度矩阵。复核了 768、1048、1319px 的六主题双语联系表；初始矩阵中的 320/1280px 状态此前已审阅。未发现插件自有裁切或重叠。
- `/etc/config/luci` 与 `/etc/config/cf_ip` 的前后哈希相同，UCI pending 状态一致。证据和报告 SHA 清单：`luci-four-repo-ui-evidence-2026-11-15/cfi-source-logs-state-theme-matrix-r22-2026-11-20/`。中央交互视觉缺口表关闭 CFI Sources / Logs 后，16 组中 2 组 CLOSED、14 组仍待完成。此次只处理该缺口，不扩展到剩余组的全断点重复截图。

### CFI Settings / Advanced 错误与成功反馈复核（2026-11-20）

- 对已安装的 r22 候选包，在最新 Bootstrap、Aurora、Vantage 六种主题模式和中英文下，完成 Settings 与 Advanced 的原生表单校验错误、保存成功反馈状态复核；使用 320×568 与 1280×900 两个主要视口，共 96 张截图、12 份零意外错误报告，八张主题/语言联系表已人工检查。其余响应宽度复用当前源码未变的 Settings/Advanced 路由矩阵。
- 无效值分别为 Download Test Count `101`（允许 1–100）与 Probe Timeout `31`（允许 1–30），由真实 LuCI 表单 Save 触发错误弹窗。成功反馈截图通过当前 LuCI 原生通知 API 显示当前语言的成功文字；没有向运行中的路由器发送 Save & Apply 请求。此前隔离实例上的实际 Save & Apply 和 UCI 回读证据继续作为独立功能证明；相关表单与 handler 在 r22 无改动。
- 设备运行包 `2.6.2-r22`、三套主题版本及 CSS SHA 已记录；/etc/config/luci 与 /etc/config/cf_ip 哈希前后相同，UCI pending 为空。报告、96 张图、联系表和逐文件 SHA 清单位于 `luci-four-repo-ui-evidence-2026-11-15/cfi-settings-advanced-r22-state-visual-2026-11-20/`。缺口表现为 16 组中 3 组 CLOSED、13 组仍待完成；按阶段工作量估算约 **93% 完成 / 7% 未完成**。Goal 继续 active。

### PM History 回滚状态当前候选视觉复核（2026-11-20）

- 在精确 PM 源码 `58c8bc7b52e0d89a3acad8cc82de18889fbda130` 的隔离 OpenWrt 当前主题实例上完成 History 待确认事务、成功回滚反馈和最终已回滚卡片视觉状态。覆盖 UI `1.0.7-r14` / All-in-One `1.0.7-r4`，六种最新主题模式 × 双语，320×568 与 1280×900；12 份报告共 72 张截图，零意外页面错误或横向溢出，六张联系表已人工审阅。
- 回滚事务列表和成功结果由符合事务 schema 的浏览器 fixture 提供；Rollback 请求在浏览器拦截，不会送达 OpenWrt daemon。该证据只证明当前视觉；实际回滚继续由隔离 runtime gate 的独立证据支撑。Vantage/Aurora 导航与固定操作栏按主题原生行为处理。
- 结束后隔离设备 `/etc/config/luci` 与 `/etc/config/performance-manager` 哈希保持不变、UCI pending 为空。逐图、报告、联系表与采集脚本 SHA-256 见 `luci-app-performance-manager/luci-four-repo-ui-evidence-2026-11-15/pm-history-rollback-r4-theme-state-2026-11-20/`。交互态缺口表现在 16 组中 4 组 CLOSED、12 组 PENDING；整体阶段估算约 **94% 完成 / 6% 未完成**。Goal 继续 active。

### 2026-11-20 验证范围收敛补充

用户确认主要断点通过即可，无需逐个相邻宽度重复拍摄。交互态复核使用手机、平板/窄桌面和常见桌面的代表尺寸；已通过的全页面矩阵继续覆盖其他断点。PM History、CFI Settings 条件字段、CFI Settings/Advanced、CFI Sources/Logs 已按最新八种主题模式补齐并更新证据清单。交互态台账当前 4/16 关闭、12/16 待处理。后续只处理剩余状态缺口，不重跑完整页面矩阵或无关宽度。


### CFI Sources CRUD 补充（2026-11-20）

复用现有 CRUD 功能交互证据，只新增当前 r22 候选包缺失的主题/语言视觉：八种主题 × 中英文 × 320×568/1280×900，共 64 张图和 16 份报告，覆盖添加弹窗与待保存来源行。没有点击 Save & Apply，设备配置哈希和 UCI pending 均未改变。Vantage 320px 的 16px 页面宽度来自主题自身 `.vt-icon-btn`，已按主题行为记录，没有改主题。交互视觉台账现为 5/16 关闭、11/16 待处理。


### Nginx Backups 状态复核（2026-11-20）

在最新主题 OpenWrt 环境的隔离副本中复用已有 r30 包，补齐八种主题、中英文、320×568/1280×900 的空状态、备份行、对比弹窗、恢复确认和恢复结果，共 160 张截图。联系表已人工复核。所有 Nginx RPC 均被浏览器拦截并由 fixture 返回，没有请求到 daemon；真实备份/恢复功能仍由原隔离交互证据证明。当前交互态台账 6/16 关闭、10/16 待处理。


### CFI PassWall Vantage 样式等价性复核（2026-11-20）

- 关闭方式采用交互状态表允许的精确源码／样式证明，避免为原生 LuCI 表单重复生成全矩阵：集成页 `passwall.js` 在真实依赖矩阵、最新主题矩阵与 r22 候选中 SHA-256 相同；只使用 LuCI `form.Map`、`form.TypedSection`、`form.Value`，没有 PassWall 专属 CSS 选择器或表单布局包装类。共享 `utils.js` 未变。
- r22 相对既有最新主题矩阵的共享 CSS 差异仅涉及 Sources/OpenClash 窄屏表头作用域及用户要求移除的页脚上边距；表头规则不匹配 PassWall 表单。Vantage Light/Dark 下当前 r22 Settings 原生表单反馈截图覆盖 320×568、1280×900，并显示同版共享页脚。既有 PassWall 真实集成矩阵保留双语、36 宽度与暂存 Save 证明；本次没有声称新增 Vantage 路由截图。未改路由器配置或服务。
- 证据：`luci-four-repo-ui-evidence-2026-11-15/cfi-passwall-vantage-source-proof-2026-11-20/`。交互状态表当前 **7/16 CLOSED、9/16 PENDING**。


### Nginx Core Config 校验与 Apply 成功态复核（2026-11-20）

- 使用精确 Nginx Manager r30 候选包与已运行的隔离 OpenWrt 克隆，覆盖八种最新主题模式 × EN/ZH × 320×568、1280×900，拍摄校验冲突弹窗和 Save & Apply 成功提示，共 64 张截图、16 份逐组合报告；四张联系表已人工复核，无意外浏览器错误、弹窗裁切或插件元素重叠。其余断点复用已有精确源码路由矩阵。
- 校验通过实际 `Custom SSL Directives Conflict` 处理器触发；成功态经过 LuCI 原生 Save & Apply 与 UCI apply/confirm，但只在隔离克隆内提交 UCI，Nginx Manager `apply_core_config` RPC 用成功 fixture 拦截，未部署或重载 Nginx。结束后 `/etc/config/nginx_manager`、`/etc/config/luci` 均恢复到镜像基线字节，UCI pending 为空；未改实际路由器。
- 证据和联系表：`luci-four-repo-ui-evidence-2026-11-15/nginx-core-config-r30-state-2026-11-20/`。交互态台账现在 **8/16 CLOSED、8/16 PENDING**。
