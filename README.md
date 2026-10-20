# Riffnel_memguard

> 面向 AI 智能体的记忆错误调查与修正验证平台
> Memory error investigation and correction verification for AI agents

**状态：开发中（v0.1 预览）。** 已可离线运行两个仿真演示；Web 界面、报告导出、基准集尚未完成。

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
| 多层残留探测 | 精确、变形、行为三层为硬性关卡，语义层仅提示待人工复核；覆盖派生摘要 |

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

## 快速开始

需要 Python 3.10+，无需联网、无需 API 密钥。

```bash
pip install -e ".[dev]"
riffnel-memguard demo stale     # 场景一：条款由 3 笔改为 6 笔，记忆过期
riffnel-memguard demo erasure   # 场景二：原始手机号已删，摘要中仍有残留
pytest
```

演示结果以退出码表示：0 为通过。分步流程（以场景一为例）：

```bash
riffnel-memguard init
riffnel-memguard ask "金卡免年费需要刷几笔？" --scope product=gold_card --at 2026-08-10
riffnel-memguard investigate inc_001
riffnel-memguard plan inc_001 --as-of 2026-09-01      # 输出 plan_xxxx
riffnel-memguard diff plan_xxxx                         # 预演
riffnel-memguard approve plan_xxxx --by <姓名>
riffnel-memguard apply plan_xxxx
riffnel-memguard verify plan_xxxx                       # 重放 + 回归
riffnel-memguard report plan_xxxx                       # .riffnel/reports/plan_xxxx.md
riffnel-memguard audit verify .riffnel/audit.db
```

Web 界面（黑白，需 `pip install -e ".[ui]"`）：`riffnel-memguard ui`，涵盖总览、事故调查、删除请求、来源更新、审计链，可审批、应用、验证并下载报告。

场景二用 `simulate-delete m_phone_raw`、`erase --subject user=u_demo --target 13800000000` 代替 `ask`/`investigate`/`plan`；来源更新后用 `revalidate --as-of <日期>`。

## 溯源、影响分析与体检

```bash
riffnel-memguard link                          # 记忆 → 条款版本（explicit / key_match / semantic）
riffnel-memguard impact cv_gw_1                # 某条款版本影响哪些记忆、派生记忆、测试题
riffnel-memguard scan --as-of 2026-09-01       # 不等事故：找出过期(M1)、冲突(M2)、无来源(M4)，生成方案
```

语义链接的相似度阈值默认 0.2，是未经验证的起始值（仿真数据中改写后的摘要得分约 0.26–0.28）。冲突（M2）只在同键、同作用域、多条有效记忆取值不同、且落败者不是「被取代的旧版本」时报告；来源无法裁定时隔离待人工复核。

## 与 memwall 配合（M6 投毒）

本项目不做写入扫描。可用 [memwall](https://github.com/gbayerv26/memwall)（MIT，独立项目，`pip install ".[memwall]"`）扫描，再导入结果：

```bash
riffnel-memguard export-memwall out.json           # 导出工作区记忆
memwall scan out.json --json report.json           # 退出码 1 表示有发现，属正常
riffnel-memguard import-memwall report.json --min-severity medium   # 生成 M6 隔离方案
```

记忆按 id 匹配，id 不同时退回「内容完全相同且唯一」匹配，匹配不到的会列出。memwall 的 JSON 结构 README 未说明，导入器按 memwall 0.6.1 实际输出编写（测试夹具见 `tests/fixtures/`）；其他版本未验证。memwall 的置信度只是按严重度映射的启发式值（0.3–0.7）。

## 部署（Docker）

```bash
docker compose up --build            # 浏览器打开 http://localhost:8501
docker run --rm $(docker build -q .) riffnel-memguard demo stale   # 只跑命令行演示
```

数据保存在容器的 `/data` 卷（`memories.json`、审计库等）；首次启动自动用仿真示例初始化。镜像为 `python:3.12-slim`，以非 root 用户运行，无需联网。

> 状态：GitHub Actions 的 `docker` 任务已构建此镜像并在容器内跑通两个演示（见仓库 Actions 页）；作者本地环境没有 Docker 服务，未在本地构建。

## 基准集（仿真）

`riffnel-memguard benchmark` 运行 64 个仿真用例（46 个事故、18 个删除），结果见 [benchmark/RESULTS.md](benchmark/RESULTS.md)，用例由 `benchmark/generate.py` 以固定种子生成。

读数前提：用例由项目维护者自行设计，事故回答由有问题的记忆脚本化生成，样本很小。结果表示流程在这些情形下能走通，**不代表真实环境的准确率**。已知弱点也列在结果里：语义层（L3）对「相差一位的其他号码」误报严重（12 个无残留用例中 6 个被它提示，而 12 个有残留用例中仅 3 个），所以它只作「待人工复核」提示，不再单独决定探测是否通过；探测的硬性关卡是精确、变形（含全角、中文数字、`at`/`dot` 写法）和行为三层。

## 当前已实现 / 未实现

| 已实现 | 未实现 |
|---|---|
| 数据模型、哈希链审计日志（含篡改检测）、JSON 参考适配器、规则抽取、字符 n-gram TF-IDF 检索 | SQLite 适配器、Mem0 / Letta 适配器 |
| 调查：M1 过期、M2 冲突、M3 串用、M4 无来源、M5 应删未删、M6 投毒（仅基础启发式） | 向量相似度（仅字符 n-gram）、LLM 抽取 |
| 溯源链接（显式 / 主题键 / 语义）、影响分析、记忆体检 `scan`（M1+M2+M4） | |
| 修正：预演、审批、应用、回滚（删除不可回滚） | 其他外部扫描工具的导入；memwall `forget-check` 的交叉校验 |
| 导入 memwall 扫描结果为 M6（已用真实 memwall 0.6.1 端到端测试） | |
| 验证：重放、回归、残留探测（精确/变形/行为 + 语义提示）、来源更新后重新验证 | HTML 报告 |
| CLI 分步命令、Markdown 证据报告（个人信息遮罩）、Streamlit 界面 | |

## 许可证

[Apache-2.0](LICENSE)

## 治理与贡献

[CONTRIBUTING](CONTRIBUTING.md) · [GOVERNANCE](GOVERNANCE.md) · [SECURITY](SECURITY.md) · [CODE_OF_CONDUCT](CODE_OF_CONDUCT.md)

## 路线图

详见 [ROADMAP.md](ROADMAP.md)。

## 声明

- 示例数据均为仿真，不代表任何真实机构。
- 本项目与任何监管机构或孵化机构无隶属或背书关系。
