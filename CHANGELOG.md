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
