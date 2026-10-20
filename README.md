# Riffnel_memguard

> 面向 AI 智能体的记忆错误调查与修正验证平台
> Memory error investigation and correction verification for AI agents

**状态：设计与开发中（v0.1-draft）。** 本仓库目前只有项目说明，代码、部署流程与演示将陆续补充。

> 原名 MemGuard。因已有同领域同名开源项目（[ac12644/MemGuard](https://github.com/ac12644/MemGuard)）及同名学术论文（[Jia 等，CCS 2019](https://arxiv.org/pdf/1909.10594)），改名为 Riffnel_memguard。本项目与它们均无关联。

## 它是什么

Riffnel_memguard **不存储记忆**。它接在现有记忆库（Mem0、Letta、自研 JSON/SQLite 存储等）之上：

1. 智能体答错时，查出是哪条记忆导致、为什么错；
2. 生成可审批、非破坏性的修正方案；
3. 用可重现的测试验证「错误已消失、且没有引入新错误」，并输出带校验链的证据报告。

## 与现有项目的关系

溯源、审计、来源漂移检测、回滚、残留检查，现有开源项目已各自实现一部分（逐项核实见 [docs/COMPETITORS.md](docs/COMPETITORS.md)）。本项目不重做这些，差异在于**把它们组合为面向事故的流程**：

| 组合点 | 说明 |
|---|---|
| 条款版本基准 | 按事故发生时间，判定当时有效的条款版本与作用域，据此归因 |
| 根因分类 M1–M6 | 过期、冲突、串用、无来源写入、应删未删、投毒 |
| 修正后批量回归 | 沿溯源图谱选出受影响题目全部重跑，而不只重放原事故 |
| 多层残留探测 | 精确、变形、语义、行为四层，覆盖派生摘要 |

## 记忆错误分类

| 代码 | 名称 |
|---|---|
| M1 | 过期 |
| M2 | 冲突 |
| M3 | 串用 |
| M4 | 无来源写入 |
| M5 | 应删未删 |
| M6 | 投毒 |

## 演示场景（全部为仿真数据）

1. 信用卡免年费条件由 3 笔改为 6 笔，智能体仍按旧记忆回答 3 笔；
2. 用户要求删除手机号，原始记录已删，摘要中仍有残留。

## 设计原则

非侵入、证据优先、非破坏性修正、人在回路、默认离线且确定性运行（LLM 为可选）、可重现、适配器可扩展。

## 快速开始 / 部署

待补充。

## 许可证

[Apache-2.0](LICENSE)

## 治理与贡献

[CONTRIBUTING](CONTRIBUTING.md) · [GOVERNANCE](GOVERNANCE.md) · [SECURITY](SECURITY.md) · [CODE_OF_CONDUCT](CODE_OF_CONDUCT.md)

## 路线图

详见 [ROADMAP.md](ROADMAP.md)。

## 声明

- 示例数据均为仿真，不代表任何真实机构。
- 本项目与任何监管机构或孵化机构无隶属或背书关系。
