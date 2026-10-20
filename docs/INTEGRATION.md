# 与相关项目的整合评估（2026-10-20）

「已核实」指项目页面或文档写明；「评估」是本项目维护者的判断。Mem0 与 Letta 的官方文档站本次无法访问，其接口只来自搜索摘要，**写适配器前须对照当前源码核实。**

| 项目 | 整合方式 | 价值（评估） | 已核实的接口依据 | 风险 / 未核实 |
|---|---|---|---|---|
| memwall | 导入其 `scan --json` 结果，作为 M6 投毒发现；`forget-check` 结果作为 L1 探测的交叉校验 | **高，成本低。** 本项目不做写入扫描，正好互补 | `scan` 支持 `--json`、`--sarif`、`--html`；`forget-check` 退出码 0/1；支持读 mem0 风格 JSON 导出与 SQLite（含 Letta、mem0 history） | JSON 字段结构 README 未写，须看实际输出；README 未描述 Python API，只能走命令行与文件 |
| Mem0 | 适配器：`list/get/update/delete/history` 映射到 `MemoryStoreAdapter` | **高。** 用户基数最大，演示说服力强 | 开源 `Memory` 类有 `get`、`get_all`、`update`、`delete`、`history`（来自第三方源码解读，旧版本）；史上记录写入 SQLite history | 当前版本签名未核实；README 称 2026-04 算法「ADD-only，无 UPDATE/DELETE」，修正动作可能只能走「删除 + 新增」 |
| Letta | 适配器：记忆块（blocks）与归档记忆（passages）的读写 | **中。** 数据结构与「事实条目」不同，须把块拆成条目；memwall 也把 Letta 列为「计划支持」 | 搜索摘要显示 SDK 有 blocks 的 retrieve/update/list、passages 的 list/create/delete | 新旧 SDK 命名不一致；未核实 Python 签名；已在路线图列 v0.2 |
| typed-recall | 适配器：`trace(answer)` 取得溯源，`forget(node_id)` 执行删除 | **中。** 溯源能直接填充本项目的检索记录与溯源图谱 | Python 示例仅有 `observe`、`bounded_generate`、`trace`、`forget`；本地 SQLite（默认 `~/.recall`）；有 MCP `audit` 工具 | **README 未写明如何列出全部记忆与节点 ID**，`trace` 入参是回答对象而非 ID，适配器能否实现 `list/search` 未知；性能数字为自述 |
| Aegis Memory | 适配器：`add`、`hybrid_query`；读取 `is_deprecated` 与来源记录 | **低到中。** 偏多智能体上下文工程，且它自带冲突扫描与合并 | `AegisClient.add/hybrid_query/scan_contradictions/consolidate_memories`；`scope`、`namespace`、`trust_level` 字段；记忆有 HMAC 签名来源记录 | README 未列 list、delete、显式废弃接口，事件日志无导出方法与格式；有两个同名项目，须确认是 quantifylabs 版 |

## 建议顺序

1. **memwall 结果导入**：与 M6 直接对应，且只依赖文件格式，v0.1 就可做。
2. **Mem0 适配器**：v0.1 可选项。须在能联网的机器上先读 `mem0/memory/main.py` 确认签名；若修正动作受限，退化为「删除 + 新增 + 记录」。
3. **typed-recall**：先验证能否列出节点，再决定。
4. **Letta、Aegis**：放 v0.2 以后。

## 不整合的原因

本项目的参考实现（JSON、SQLite）已能完整演示。整合是加分项，不应影响 10-31 的交付。
