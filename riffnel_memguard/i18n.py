"""Translations for the web UI and the evidence report: Chinese (the source text), English and Brazilian Portuguese.

`tr(lang, zh_text, **fmt)` looks the Chinese text up and returns the English or Portuguese version; an untranslated text
falls back to Chinese, so a missing entry degrades gracefully instead of crashing. The Portuguese was written by the
project's author without a native review: have a Portuguese speaker check it before using it in front of customers.
"""
from __future__ import annotations

LANGS = {"zh": "中文", "en": "English", "pt": "Português"}

_E = "en"
_P = "pt"

_TR: dict[str, dict[str, str]] = {
    # ---- common
    "通过": {_E: "passed", _P: "aprovado"},
    "失败": {_E: "failed", _P: "reprovado"},
    "审批人": {_E: "Approver", _P: "Aprovador"},
    "审批": {_E: "Approve", _P: "Aprovar"},
    "应用": {_E: "Apply", _P: "Aplicar"},
    "验证": {_E: "Verify", _P: "Verificar"},
    "回滚": {_E: "Roll back", _P: "Reverter"},
    "状态": {_E: "Status", _P: "Situação"},
    "类型": {_E: "Kind", _P: "Tipo"},
    "作用域": {_E: "Scope", _P: "Escopo"},
    "内容": {_E: "Content", _P: "Conteúdo"},
    "发现": {_E: "Findings", _P: "Achados"},
    "示例数据均为仿真。": {_E: "All example data is simulated.", _P: "Todos os dados de exemplo são simulados."},
    # ---- sidebar / pages
    "页面": {_E: "Page", _P: "Página"},
    "总览": {_E: "Overview", _P: "Visão geral"},
    "事故调查": {_E: "Incident investigation", _P: "Investigação de incidente"},
    "跨语言一致性": {_E: "Cross-lingual consistency", _P: "Consistência entre idiomas"},
    "删除请求": {_E: "Erasure request", _P: "Pedido de eliminação"},
    "来源更新": {_E: "Source updates", _P: "Atualização de fontes"},
    "审计链": {_E: "Audit chain", _P: "Cadeia de auditoria"},
    "外部智能体（可选）": {_E: "External agent (optional)", _P: "Agente externo (opcional)"},
    "Web 界面默认不执行外部命令（防止远程执行）。在本机可信环境设置 RIFFNEL_UI_ALLOW_AGENT_CMD=1 后启用；命令行 `--agent-cmd` 不受此限制。": {
        _E: "The web UI does not run external commands by default (to prevent remote execution). On a trusted local machine set RIFFNEL_UI_ALLOW_AGENT_CMD=1 to enable it; the command-line `--agent-cmd` is not affected.",
        _P: "Por padrão a interface web não executa comandos externos (para evitar execução remota). Em uma máquina local confiável, defina RIFFNEL_UI_ALLOW_AGENT_CMD=1 para habilitar; o `--agent-cmd` da linha de comando não é afetado."},
    "命令（留空使用内置示例智能体）": {_E: "Command (empty = built-in example agent)", _P: "Comando (vazio = agente de exemplo embutido)"},
    "协议见 README：标准输入一行 JSON，标准输出最后一行 JSON": {
        _E: "Protocol in the README: one JSON line on stdin, the last stdout line is JSON",
        _P: "Protocolo no README: uma linha JSON na entrada padrão; a última linha da saída padrão é JSON"},
    "每次调用超时（秒）": {_E: "Timeout per call (seconds)", _P: "Tempo limite por chamada (segundos)"},
    "工作区 {root} 尚未初始化": {_E: "Workspace {root} is not initialized", _P: "O espaço de trabalho {root} não foi inicializado"},
    "用仿真示例初始化": {_E: "Initialize with the simulated example", _P: "Inicializar com o exemplo simulado"},
    "用巴西仿真示例初始化（中/葡/英）": {_E: "Initialize with the simulated Brazilian example (zh/pt/en)",
                                      _P: "Inicializar com o exemplo brasileiro simulado (zh/pt/en)"},
    # ---- chat demo
    "对话演示": {_E: "Chat demo", _P: "Demonstração em chat"},
    "像和客服智能体聊天一样提问；再让 Riffnel 用每种语言各问一遍，找出落后的那一种并修正。": {
        _E: "Chat with the customer-service agent as usual; then let Riffnel ask the same question in every language, find the one that is behind, and fix it.",
        _P: "Converse com o agente de atendimento como de costume; depois o Riffnel faz a mesma pergunta em cada idioma, encontra o que está desatualizado e o corrige."},
    "与当时有效的条款一致": {_E: "Matches the clause valid at that date", _P: "Conforme a cláusula vigente na data"},
    "与当时有效的条款不符": {_E: "Does not match the clause valid at that date", _P: "Diverge da cláusula vigente na data"},
    "向智能体提问……": {_E: "Ask the agent…", _P: "Pergunte ao agente…"},
    "用每种语言各问一遍": {_E: "Ask in every language", _P: "Perguntar em cada idioma"},
    "用 Riffnel 修正并复查": {_E: "Fix with Riffnel and re-check", _P: "Corrigir com o Riffnel e reverificar"},
    "已修正并复查：{plan}": {_E: "Fixed and re-checked: {plan}", _P: "Corrigido e reverificado: {plan}"},
    "清空对话": {_E: "Clear chat", _P: "Limpar conversa"},
    # ---- plan panel
    "修正方案 {plan_id}　状态：{status}": {_E: "Correction plan {plan_id}  Status: {status}", _P: "Plano de correção {plan_id}  Situação: {status}"},
    "已清除工作区状态中含目标值的 {n} 处文本，删除含目标值的报告 {m} 份。": {
        _E: "Removed {n} text(s) containing the erased value from the workspace state and deleted {m} report(s) that contained it.",
        _P: "Removidos {n} texto(s) com o valor eliminado do estado do espaço de trabalho e {m} relatório(s) que o continham."},
    "应用中途失败，方案处于 apply_failed。修复原因后再次点击「应用」会从断点继续，或点击「回滚」撤销已完成的部分。": {
        _E: "Applying failed part-way; the plan is apply_failed. After fixing the cause, click Apply again to resume, or Roll back to undo the completed part.",
        _P: "A aplicação falhou no meio; o plano está em apply_failed. Corrija a causa e clique em Aplicar para retomar, ou em Reverter para desfazer a parte concluída."},
    "该方案的验证需要执行外部智能体命令，Web 界面默认不执行（设置 RIFFNEL_UI_ALLOW_AGENT_CMD=1 启用，或改用命令行 verify）。": {
        _E: "Verifying this plan needs to run an external agent command, which the web UI does not do by default (set RIFFNEL_UI_ALLOW_AGENT_CMD=1, or use the command-line verify).",
        _P: "A verificação deste plano exige executar um comando de agente externo, o que a interface web não faz por padrão (defina RIFFNEL_UI_ALLOW_AGENT_CMD=1 ou use o verify da linha de comando)."},
    "无法回滚的删除：{skipped}": {_E: "Deletions that cannot be rolled back: {skipped}", _P: "Eliminações que não podem ser revertidas: {skipped}"},
    "已回滚": {_E: "Rolled back", _P: "Revertido"},
    "目标值暂存在工作区 secrets/（权限 0600），验证通过后自动清除。": {
        _E: "The target values are kept in the workspace secrets/ folder (mode 0600) and removed automatically once verification passes.",
        _P: "Os valores-alvo ficam na pasta secrets/ do espaço de trabalho (modo 0600) e são removidos automaticamente após a verificação."},
    "丢弃目标值（不再验证）": {_E: "Discard target values (skip verification)", _P: "Descartar valores-alvo (sem verificar)"},
    "语义层（L3）提示，待人工复核：{items}": {_E: "Semantic layer (L3) hint, needs human review: {items}", _P: "Dica da camada semântica (L3), requer revisão humana: {items}"},
    "生成证据报告": {_E: "Generate evidence report", _P: "Gerar relatório de evidências"},
    "下载 Markdown 报告": {_E: "Download Markdown report", _P: "Baixar relatório em Markdown"},
    # ---- overview / incident
    "记忆 {m} 条　事故 {i} 个　方案 {p} 个": {_E: "{m} memories  {i} incidents  {p} plans", _P: "{m} memórias  {i} incidentes  {p} planos"},
    "方案": {_E: "Plans", _P: "Planos"},
    "问题": {_E: "Question", _P: "Pergunta"},
    "作用域 (key=value, 逗号分隔)": {_E: "Scope (key=value, comma separated)", _P: "Escopo (chave=valor, separado por vírgula)"},
    "事故日期": {_E: "Incident date", _P: "Data do incidente"},
    "提问并记录事故": {_E: "Ask and record the incident", _P: "Perguntar e registrar o incidente"},
    "事故": {_E: "Incident", _P: "Incidente"},
    "智能体：": {_E: "Agent: ", _P: "Agente: "},
    "外部命令 `{cmd}`": {_E: "external command `{cmd}`", _P: "comando externo `{cmd}`"},
    "内置示例智能体": {_E: "built-in example agent", _P: "agente de exemplo embutido"},
    "问：{q}": {_E: "Q: {q}", _P: "P: {q}"},
    "答：{a}　取用记忆：{ids}": {_E: "A: {a}  Memories used: {ids}", _P: "R: {a}  Memórias usadas: {ids}"},
    "调查": {_E: "Investigate", _P: "Investigar"},
    "置信度 {c}": {_E: "confidence {c}", _P: "confiança {c}"},
    "记忆：{t}": {_E: "Memory: {t}", _P: "Memória: {t}"},
    "当时有效条款（{v}）：{t}": {_E: "Clause valid at that time ({v}): {t}", _P: "Cláusula vigente na época ({v}): {t}"},
    "无法归因：错误不来自被取用的记忆。": {_E: "Not attributable: the error does not come from the retrieved memories.",
                                       _P: "Não atribuível: o erro não vem das memórias recuperadas."},
    "修正生效日期": {_E: "Correction effective date", _P: "Data de vigência da correção"},
    "生成修正方案": {_E: "Draft correction plan", _P: "Gerar plano de correção"},
    # ---- erasure
    "数据主体作用域": {_E: "Data subject scope", _P: "Escopo do titular dos dados"},
    "需消失的值（精确）": {_E: "Value that must disappear (exact)", _P: "Valor que deve desaparecer (exato)"},
    "语义探测描述": {_E: "Semantic probe description", _P: "Descrição da sonda semântica"},
    "登记并查残留": {_E: "Register and look for residue", _P: "Registrar e procurar resíduos"},
    "发现 {n} 处残留": {_E: "{n} residue(s) found", _P: "{n} resíduo(s) encontrado(s)"},
    "未发现残留": {_E: "No residue found", _P: "Nenhum resíduo encontrado"},
    # ---- source updates
    "检查日期": {_E: "Check date", _P: "Data da verificação"},
    "找出依赖旧版本的记忆": {_E: "Find memories that depend on an old version", _P: "Encontrar memórias que dependem de uma versão antiga"},
    "{n} 条记忆过期": {_E: "{n} stale memories", _P: "{n} memória(s) desatualizada(s)"},
    "没有依赖旧版本的有效记忆": {_E: "No active memory depends on an old version", _P: "Nenhuma memória ativa depende de uma versão antiga"},
    "全面体检（过期 / 冲突 / 无来源）": {_E: "Full health scan (stale / conflict / unsupported)", _P: "Verificação completa (desatualizada / conflito / sem fonte)"},
    "未发现问题": {_E: "No problem found", _P: "Nenhum problema encontrado"},
    # ---- audit
    "校验通过": {_E: "Verified", _P: "Verificada"},
    "第 {n} 条异常": {_E: "Event {n} is invalid", _P: "O evento {n} é inválido"},
    "时间": {_E: "Time", _P: "Hora"}, "操作者": {_E: "Actor", _P: "Autor"}, "动作": {_E: "Action", _P: "Ação"},
    "对象类型": {_E: "Object type", _P: "Tipo de objeto"}, "对象": {_E: "Object", _P: "Objeto"},
    "载荷哈希": {_E: "Payload hash", _P: "Hash do conteúdo"}, "前哈希": {_E: "Previous hash", _P: "Hash anterior"}, "哈希": {_E: "Hash", _P: "Hash"},
    # ---- cross-lingual page
    "同一个事实用多种语言各问一次，比较智能体的回答是否一致、是否与当时有效的条款一致。": {
        _E: "Ask the same fact in several languages and compare the agent's answers: are they consistent with each other and with the clause valid at that date?",
        _P: "Pergunte o mesmo fato em vários idiomas e compare as respostas do agente: são consistentes entre si e com a cláusula vigente naquela data?"},
    "此工作区没有跨语言检查。用 `riffnel-memguard init --example bank_br` 创建巴西示例，或在工作区放入 i18n_checks.json。": {
        _E: "This workspace has no cross-lingual checks. Create the Brazilian example with `riffnel-memguard init --example bank_br`, or add an i18n_checks.json.",
        _P: "Este espaço de trabalho não tem verificações entre idiomas. Crie o exemplo brasileiro com `riffnel-memguard init --example bank_br` ou adicione um i18n_checks.json."},
    "以此日期的条款为准": {_E: "Use the clauses valid on this date", _P: "Usar as cláusulas vigentes nesta data"},
    "运行跨语言检查": {_E: "Run the cross-lingual check", _P: "Executar a verificação entre idiomas"},
    "应为 {v}": {_E: "expected {v}", _P: "esperado {v}"},
    "语言": {_E: "Language", _P: "Idioma"},
    "答案": {_E: "Answer", _P: "Resposta"},
    "数字": {_E: "Number", _P: "Número"},
    "正确": {_E: "Correct", _P: "Correto"},
    "各语言一致且正确": {_E: "Consistent and correct in every language", _P: "Consistente e correto em todos os idiomas"},
    "不一致：{langs} 与有效条款不符": {_E: "Inconsistent: {langs} disagree(s) with the valid clause", _P: "Inconsistente: {langs} diverge(m) da cláusula vigente"},
    "责任记忆": {_E: "Responsible memories", _P: "Memórias responsáveis"},
    "（{l}）": {_E: "({l})", _P: "({l})"},
    "各语言答案一致且正确，没有需要修正的。": {_E: "The answers are consistent and correct in every language: nothing to fix.",
                                          _P: "As respostas são consistentes e corretas em todos os idiomas: nada a corrigir."},
    "复查：{v}": {_E: "Re-check: {v}", _P: "Nova verificação: {v}"},
    # ---- report
    "证据报告 {id}": {_E: "Evidence report {id}", _P: "Relatório de evidências {id}"},
    "状态：{s}　审批人：{a}": {_E: "Status: {s}  Approver: {a}", _P: "Situação: {s}  Aprovador: {a}"},
    "1. 摘要": {_E: "1. Summary", _P: "1. Resumo"},
    "- 发现：{n} 条（类别 {c}）": {_E: "- Findings: {n} (classes {c})", _P: "- Achados: {n} (classes {c})"},
    "无": {_E: "none", _P: "nenhuma"},
    "- 修正动作：{n} 个": {_E: "- Correction actions: {n}", _P: "- Ações de correção: {n}"},
    "- 验证：{v}": {_E: "- Verification: {v}", _P: "- Verificação: {v}"},
    "- 验证：尚未执行": {_E: "- Verification: not run yet", _P: "- Verificação: ainda não executada"},
    "2. 事故 / 请求": {_E: "2. Incident / request", _P: "2. Incidente / pedido"},
    "- 时间：{t}　作用域：{s}": {_E: "- Time: {t}  Scope: {s}", _P: "- Data: {t}  Escopo: {s}"},
    "- 问：{q}": {_E: "- Question: {q}", _P: "- Pergunta: {q}"},
    "- 答：{a}": {_E: "- Answer: {a}", _P: "- Resposta: {a}"},
    "- 删除请求 {id}：对象 {s}，目标（已遮罩）{t}": {_E: "- Erasure request {id}: subject {s}, targets (masked) {t}",
                                               _P: "- Pedido de eliminação {id}: titular {s}, alvos (mascarados) {t}"},
    "3. 证据": {_E: "3. Evidence", _P: "3. Evidências"},
    "- **{c}** 记忆 `{m}`（置信度 {conf}）": {_E: "- **{c}** memory `{m}` (confidence {conf})", _P: "- **{c}** memória `{m}` (confiança {conf})"},
    "  - 记忆原文：{t}": {_E: "  - Memory text: {t}", _P: "  - Texto da memória: {t}"},
    "  - 当时有效条款（{v}）：{t}": {_E: "  - Clause valid at that time ({v}): {t}", _P: "  - Cláusula vigente na época ({v}): {t}"},
    "  - 记忆对应旧版本：{v}": {_E: "  - The memory matches the old version: {v}", _P: "  - A memória corresponde à versão antiga: {v}"},
    "  - 语言：{l}": {_E: "  - Language: {l}", _P: "  - Idioma: {l}"},
    "  - 外部扫描（{src} {ver}，严重度 {sev}）：{r}": {_E: "  - External scan ({src} {ver}, severity {sev}): {r}", _P: "  - Varredura externa ({src} {ver}, gravidade {sev}): {r}"},
    "  - 残留匹配方式：{m}；目标 {t}": {_E: "  - Residue match: {m}; targets {t}", _P: "  - Tipo de correspondência do resíduo: {m}; alvos {t}"},
    "4. 修正方案": {_E: "4. Correction plan", _P: "4. Plano de correção"},
    "5. 验证": {_E: "5. Verification", _P: "5. Verificação"},
    "- 重放：{r}；回答：{a}": {_E: "- Replay: {r}; answer: {a}", _P: "- Repetição: {r}; resposta: {a}"},
    "- 回归：{r}（受影响 {a}，未受影响 {u}）": {_E: "- Regression: {r} (affected {a}, unaffected {u})", _P: "- Regressão: {r} (afetados {a}, não afetados {u})"},
    "- 残留探测：{r}（L1={l1} L2={l2} L4={l4}）": {_E: "- Residue probe: {r} (L1={l1} L2={l2} L4={l4})", _P: "- Sonda de resíduos: {r} (L1={l1} L2={l2} L4={l4})"},
    "硬性关卡均无命中": {_E: "no hit in the hard gates", _P: "nenhum resultado nas barreiras obrigatórias"},
    "仍有残留": {_E: "residue remains", _P: "ainda há resíduos"},
    "- 语义层（L3）提示，待人工复核：{items}": {_E: "- Semantic layer (L3) hint, needs human review: {items}", _P: "- Dica da camada semântica (L3), requer revisão humana: {items}"},
    "- 跨语言一致性：{r}": {_E: "- Cross-lingual consistency: {r}", _P: "- Consistência entre idiomas: {r}"},
    "  - {id}（应为 {e}）：{vals}": {_E: "  - {id} (expected {e}): {vals}", _P: "  - {id} (esperado {e}): {vals}"},
    "6. 可重现信息": {_E: "6. Reproducibility", _P: "6. Reprodutibilidade"},
    "- 修正前快照 SHA-256：`{h}`": {_E: "- Snapshot before the correction, SHA-256: `{h}`", _P: "- Instantâneo antes da correção, SHA-256: `{h}`"},
    "- 修正后快照 SHA-256：`{h}`": {_E: "- Snapshot after the correction, SHA-256: `{h}`", _P: "- Instantâneo depois da correção, SHA-256: `{h}`"},
    "- 生效日期（as_of）：{d}": {_E: "- Effective date (as_of): {d}", _P: "- Data de vigência (as_of): {d}"},
    "- 检索：字符 2–3 gram TF-IDF，确定性，无随机性；无 LLM": {
        _E: "- Retrieval: character 2–3-gram TF-IDF, deterministic, no randomness; no LLM",
        _P: "- Recuperação: TF-IDF de n-gramas de 2–3 caracteres, determinística, sem aleatoriedade; sem LLM"},
    "7. 审计链": {_E: "7. Audit chain", _P: "7. Cadeia de auditoria"},
    "校验：`riffnel-memguard audit verify <ws>/audit.db`": {_E: "Verify with: `riffnel-memguard audit verify <ws>/audit.db`",
                                                           _P: "Verifique com: `riffnel-memguard audit verify <ws>/audit.db`"},
}


def tr(lang: str, zh: str, **fmt) -> str:
    """The text in `lang` ('zh', 'en' or 'pt'), formatted with `fmt`; untranslated text stays Chinese."""
    text = zh if lang == "zh" else _TR.get(zh, {}).get(lang, zh)
    return text.format(**fmt) if fmt else text


def missing(lang: str, texts: list[str]) -> list[str]:
    """Texts without a translation into `lang` (used by tests)."""
    return [t for t in texts if lang != "zh" and lang not in _TR.get(t, {})]
