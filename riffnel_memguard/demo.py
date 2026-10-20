"""Offline demos on simulated data: `stale` (M1) and `erasure` (M5)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from .adapters.base import JsonFileStore
from .agent.bank import BankAssistAgent
from .core.audit import AuditLog
from .core.models import Incident, Source, TestCase
from .engines import corrector, investigator, verifier
from .probes.erasure import mask

EXAMPLES = Path(__file__).resolve().parent / "examples" / "bank"


def _setup(workdir: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copy(EXAMPLES / "memories.json", workdir / "memories.json")
    store = JsonFileStore(workdir / "memories.json")
    sources = [Source(**s) for s in json.loads((EXAMPLES / "sources.json").read_text(encoding="utf-8"))]
    clauses = [c for s in sources for c in s.clauses]
    tests = [TestCase(**t) for t in json.loads((EXAMPLES / "tests.json").read_text(encoding="utf-8"))]
    audit = AuditLog(workdir / "audit.db")
    return store, clauses, tests, audit


def run_stale(workdir: Path, log=print) -> dict:
    """Scenario 1: gold-card waiver changed from 3 to 6 transactions on 2026-07-01; agent still says 3."""
    store, clauses, tests, audit = _setup(workdir)
    agent = BankAssistAgent(store)
    by_key = {c.key: c for c in clauses}
    scope, occurred, as_of = {"product": "gold_card"}, "2026-08-10", "2026-09-01"

    q = "金卡免年费需要刷几笔？"
    answer, retrieved = agent.answer(q, scope)
    inc = Incident(id="inc_001", occurred_at=occurred, agent_id="bank-bot", scope=scope,
                   question=q, answer=answer, retrieved_ids=retrieved)
    log(f"[事故] 问：{q}\n       答：{answer}")

    findings = investigator.investigate(inc, store, clauses)
    for f in findings:
        log(f"[调查] {f.cls} 记忆 {f.memory_id}（置信度 {f.confidence}）：现行 {f.evidence['valid_version']} 为"
            f" {f.evidence['valid_value']}，记忆写的是旧值")
    plan = corrector.make_plan(findings, store, inc.id, by_key, as_of)
    audit.append("system", "plan", "plan", plan.id)
    log("[修正方案预演]\n  " + "\n  ".join(corrector.diff(plan, store)))
    before = verifier.snapshot_sha(store)
    corrector.approve(plan, "demo-reviewer", audit)
    corrector.apply(plan, store, audit)
    after = verifier.snapshot_sha(store)

    rep = verifier.replay(agent, inc, clauses, as_of)
    reg = verifier.regression(agent, tests, {f.evidence["key"] for f in findings})
    log(f"[重放] {'通过' if rep['passed'] else '失败'}：{rep['answer']}")
    log(f"[回归] {'通过' if reg['passed'] else '失败'}：受影响题 {reg['affected']}，未受影响题 {reg['unaffected']}")
    ok, bad = audit.verify()
    log(f"[审计链] {'完整' if ok else f'第 {bad} 条异常'}（{len(audit.events())} 条事件）")
    return {"incident": inc, "findings": findings, "plan": plan, "replay": rep, "regression": reg,
            "snapshot_before": before, "snapshot_after": after, "audit_ok": ok,
            "passed": bool(findings) and rep["passed"] and reg["passed"] and ok}


def run_erasure(workdir: Path, log=print) -> dict:
    """Scenario 2: the raw phone record was deleted, but a derived summary still holds the number."""
    store, clauses, tests, audit = _setup(workdir)
    agent = BankAssistAgent(store)
    scope, targets = {"user": "u_demo"}, ["13800000000"]
    desc, questions = "客户张三的手机号 13800000000", ["我的手机号是多少？"]

    store.delete("m_phone_raw")  # the upstream deletion that only removed the raw record
    audit.append("system", "erasure_request", "subject", "u_demo")
    log(f"[删除请求] 目标 {mask(targets[0])}；原始记录已删除")
    pre = verifier.erasure(store, agent, scope, targets, desc, questions)
    log(f"[探测·修正前] L1={pre['L1_exact']} L2={pre['L2_variant']} L3={[i for i, _ in pre['L3_semantic']]} L4={pre['L4_behavior']}")

    findings = investigator.investigate_erasure(store, targets)
    plan = corrector.make_plan(findings, store, None, {}, "2026-09-01")
    log("[修正方案预演]\n  " + "\n  ".join(corrector.diff(plan, store)))
    corrector.approve(plan, "demo-reviewer", audit)
    corrector.apply(plan, store, audit)

    post = verifier.erasure(store, agent, scope, targets, desc, questions)
    log(f"[探测·修正后] {'四层均无命中' if post['passed'] else '仍有残留'}")
    ok, bad = audit.verify()
    log(f"[审计链] {'完整' if ok else f'第 {bad} 条异常'}")
    return {"findings": findings, "plan": plan, "pre": pre, "post": post, "audit_ok": ok,
            "passed": (not pre["clean"]) and bool(findings) and post["passed"] and ok}
