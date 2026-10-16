# G3 PM Runtime 包影响验证

PM 继续使用 Stable 协议；不切换 Preview，不合并当前分支领先 main 的其他开发。生产锁仍保持旧资格身份，待新的真实 hosted package commit/run/attempt 后再同步。

实际 SDK Full 包与本轮 Stable 包含同一 Runtime 字节，摘要为 `bcc587dbbeab6da71e6c3b1113db2037b69e7bec3e01f696e0e9a5d3cce1561b`。实际 Full/Core/LuCI/glue/Stable 五包 metadata 检查通过。Full 的负依赖包含 Stable、Preview 和拆分包，APK 解析器保留真实 conflict bit，不能误认正向依赖。

真实 APK 隔离根验证六种顺序：Full→Stable、Stable→Full、Full→Preview、Preview→Full、Full→split、split→Full。所有冲突拒绝后 installed set、world、Runtime/Core/config 摘要保持；卸载重装保留独立用户状态。依赖由实际 SDK 包解析，没有假 provider。首次缺 coreutils-timeout 的失败保留在临时执行根；构建实际依赖后才重验通过。

当前 PM 181 项单测通过。其内部 mock 的 verdict 不是真实设备或 hosted 资格；实际包事务结果独立保存。

证据索引：`g3-runtime-package-evidence/index.json`。包脚本未执行，签名、服务、LuCI、真实设备、持续运行及新 hosted 精确提交资格均未验证。G3 尚未完成；不发布、不伪造消费者新锁。
