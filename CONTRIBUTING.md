# 贡献指南

流程：Issue → 讨论 → Pull Request → 审查 → 合并。

1. 先开 Issue 说明问题或想法，避免重复工作。
2. Fork 后从 `main` 开分支，保持改动小而聚焦。
3. 本地运行 `pip install -e ".[dev]" && pytest`，新增功能请附测试。
4. 示例与基准数据必须标明「仿真」，不得包含真实个人信息。
5. 新增依赖须在 PR 中说明其许可证，并更新 `THIRD_PARTY_LICENSES.md`。

提交的贡献视为按 Apache-2.0 授权。
