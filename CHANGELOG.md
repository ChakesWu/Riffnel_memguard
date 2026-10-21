# Changelog

## Unreleased
- 项目初始化（原名 MemGuard，已改名 Riffnel_memguard）：README、Apache-2.0 许可证、包骨架、CI。
- 核心引擎：审计链、JSON 适配器、调查（M1/M3/M4/M5/M6）、修正、验证、两个演示场景。
- 分步 CLI（ask/investigate/plan/diff/approve/apply/verify/report/revalidate/erase）与 Markdown 证据报告。
- 仿真基准集（60 例）与 `benchmark` 命令；M3 改为按条款作用域检测并用 rescope 修正；修正时已有正确记忆则不重复新增。
- Streamlit 界面（黑白）；流程逻辑抽到 `service` 模块，CLI 与界面共用。
- Dockerfile、docker-compose、CI 镜像构建任务；示例数据移入包内（`riffnel_memguard/examples`），支持非 editable 安装。
- memwall 集成：`export-memwall` / `import-memwall`（M6），含真实 memwall 0.6.1 端到端测试。
- 溯源链接器、影响分析、M2 冲突检测、`link`/`impact`/`scan` 命令；基准集增至 64 例（新增 M2 与溯源指标）。
- 修复：规则抽取支持中文数字（三笔）；残留探测规范化覆盖中文数字与 at/dot 写法（困难用例 0/2 → 2/2）；语义层 L3 降为人工复核提示（近似号码用例误报 6/12）；README 中 Docker 状态更正（CI 已构建并跑通）。基准集增至 74 例。
- 真实堆栈：Mem0 适配器、Pydantic AI 企业客服智能体、检索追踪、`demo real-stale` / `real-erasure`；残留探测纳入 Mem0 历史库；修复修正方案重复新增/停用；强制关闭 Mem0 遥测。
- SQLite 适配器（可映射已有表）与 `demo sqlite-stale/sqlite-erasure`；`agent` extra 含 openai 以支持 `deepseek:` 等模型串；记录 Letta 无法在当前环境验证的原因。
- 真实模型（DeepSeek）验证 `real-stale`；修复回归比对对空白与 Markdown 敏感的缺陷（真实模型下回归 6/10 → 10/10）。
- 真实嵌入器（Mem0 fastembed + BAAI/bge-small-zh-v1.5）与真实 DeepSeek 模型组合验证两个场景；`make_memory(embedder=...)`；真实堆栈失败时给出更准确的错误说明。
- `--agent-cmd`：以命令接入任意语言的外部智能体（`ask`/`verify`），含参考实现与 Node.js 示例；Mem0 适配器不再静默截断（自适应放大上限，到顶报错）、单条查找不列全表、启动时检查版本；extras 固定到已测试的小版本。
- Letta 适配器（归档记忆，标签保存字段、替换式修改、游标分页）、`demo letta-stale/letta-erasure`、真实 Letta 服务端上的 6 项集成测试与可复现的测试环境脚本；Web 界面可接入外部智能体（默认关闭，防远程执行）。
- 安全与可靠性修复（对照工具自己的说法检查得出）：删除后清除工作区内的目标值副本（`secrets/` 暂存、`state.json` 与报告清除）、强制方案状态机与审批人政策、日志式可恢复应用、文件锁与原子写入、审计 HMAC 与链头、`--target-file`、邮箱遮罩；14 项回归测试。
- 修复：`agent` extra 的版本固定按 Python 版本分别设置（pydantic-ai-slim 2.55 起要求 Python 3.11，原固定使 Python 3.10 无法安装）。
