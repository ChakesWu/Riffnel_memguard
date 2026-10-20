# 相关项目核实（2026-10-20）

核实方法：访问各项目 GitHub 或 PyPI 页面，只记录页面上写明的内容。页面未写的写「页面未提及」，不代表该项目没有此功能。

| 项目 | 许可证 | 页面所述能力 | 页面未提及 / 未核实 |
|---|---|---|---|
| [Mem0](https://github.com/mem0ai/mem0) | Apache-2.0 | 记忆层；2026 年 4 月算法为「单次 ADD-only 抽取，无 UPDATE/DELETE，记忆累积」；时间感知检索 | 冲突处理、历史、删除、溯源（README 未写） |
| [Letta](https://github.com/letta-ai/letta) | Apache-2.0 | 有状态智能体平台，记忆持久化 | 记忆检查与调试功能（README 未写，指向 docs.letta.com，未核实） |
| [memwall](https://github.com/gbayerv26/memwall) | MIT | 扫描记忆（规则 MW001–MW016）；MCP 写入网关与隔离；追加式审计；`forget-check` 按字面标识符查残留；离线试验（记忆是否有益或有害） | README 称其「无法证明改写或语义层面的删除」，并提到源行删除后名字可能留在摘要中；未见修正后重放与回归 |
| [typed-recall](https://github.com/yash194/recall)（PyPI 名 typed-recall） | Apache-2.0 | 类型化边图谱；`trace(answer)` 溯源；`forget(node_id)` 精准遗忘并写审计；追加式可导出日志 | 遗忘是否真的清除的验证方法（页面未提及）；性能数字为项目自述 |
| [aegis-memory (quantifylabs)](https://github.com/quantifylabs/aegis-memory) | Apache-2.0 | 不可变事件日志；合并后旧记忆标记 `is_deprecated` 仍可查；HMAC 签名的来源记录；完整性哈希 | 删除与擦除（页面未提及）。另有同名项目 lavadman/aegis-memory，与此不同 |
| [memory-blackbox](https://github.com/lavkumarv/agent-forensics) | Apache-2.0 | 追加式防篡改账本；`trace` 把坏动作追溯到源头记忆写入；`rollback`（默认预演，只追加不删除）；回滚后重跑有害动作并显示「不再有害」 | 早期开发，API 未稳定 |
| [ac12644/MemGuard](https://github.com/ac12644/MemGuard) | Apache-2.0 | **同名项目。** 对 Mem0、Zep、Letta、LangMem 的记忆按来源 URL 重新抓取并比对值；信任分数；低于 30% 自动隔离；审计链 | 删除、修正后重放或回归（页面未提及）。页面显示 3 stars、10 commits、无 release |
| [agentmem](https://github.com/Thezenmonster/agentmem) | MIT | 记忆存 `source_path` 与 `source_hash`，哈希变化时更新或弃用；冲突检测；生命周期状态 | 专门的修正后验证流程（页面未提及） |
| [mneme](https://github.com/HarperZ9/mneme) | FSL-1.1-MIT（fair-source，保留商业使用权） | `mneme drift` 检查记忆引用的来源是否变化（MATCH/DRIFT/UNVERIFIABLE） | 修正流程。**许可证限制商业使用，不宜依赖或借鉴代码** |
| [inspeximus](https://github.com/DanceNitra/inspeximus) | MIT | 擦除证书（签名、无内容的墓碑）；`scan_residue` 字面匹配，分 LIVE/UNRECLAIMED/PLAIN | 页面自述证明仅覆盖本存储，不含向量索引、提示日志、备份。**未读完整页**（后 18964 字符未读） |
| Ferryte（[PyPI](https://pypi.org/project/ferryte)） | 据搜索摘要：MIT 引擎、open-core | 据搜索摘要：植入 canary 记忆、触发删除、探测智能体并检查存储与检索轨迹、追踪派生物 | **页面无法加载，以上全部来自搜索摘要，未核实。** 与本项目「删除验证」重叠最大 |
| 论文：Deployment-Time Memorization（[arXiv 2606.10062](https://arxiv.org/pdf/2606.10062)） | — | 据搜索摘要：定义 Forgetting Residue Score；只删原始记录时摘要中约 20% 实例仍可恢复 | 仅读搜索摘要，未读原文 |
| 论文：STALE（[arXiv 2605.06527](https://arxiv.org/html/2605.06527v1)） | — | 评测智能体能否识别过期记忆（400 个冲突场景） | 仅读搜索摘要 |

## 对 MemGuard 创新点的影响（如实结论）

1. **「以权威来源版本为基准」：部分已有。** ac12644/MemGuard、agentmem、mneme 都做来源变化检测。MemGuard 的差异只能是「带有效期的条款版本 + 作用域，按事故发生时间判定当时有效版本」，不能说成首创。
2. **「调查→修正→验证闭环」：memory-blackbox 已有追溯→回滚→重跑。** MemGuard 的差异只能是：根因分类 M1–M6、条款版本基准、回归题批量重跑、审批流程。不能说成首个闭环。
3. **「四层残留探测」：memwall、inspeximus、Ferryte 都有残留或遗忘检查。** 差异只能是四层组合（含语义与行为层）和报告形式。Ferryte 未核实，写入正式文档前须再核。
4. **名称冲突是实质问题。** 存在同领域同名项目 ac12644/MemGuard，另有 2019 年同名学术论文（[Jia 等，CCS 2019](https://arxiv.org/pdf/1909.10594)）。建议改名。
5. **Mem0 / Letta 的描述需修正：** 原设计文档写「Mem0 冲突时旧事实标记失效」「Letta 可视化调试」，本次核实 README 均未写明，不得再这样写。
