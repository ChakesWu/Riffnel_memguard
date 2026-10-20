"""End-to-end scenarios on a real stack: Mem0 (Apache-2.0) + local Qdrant + a Pydantic AI agent.

Data is simulated (the example bank). The memory layer and the agent framework are real code paths. The language model
is the deterministic `OfflineStandIn` unless RIFFNEL_AGENT_MODEL is set.
"""
from __future__ import annotations

import json
from pathlib import Path

import os

from .adapters.mem0_adapter import Mem0Adapter, make_memory
from .agent.enterprise import EnterpriseBankAgent
from .agent.trace import capture
from .core.audit import AuditLog
from .core.models import MemoryRecord, Source, TestCase
from .demo import EXAMPLES
from .engines import corrector, investigator, verifier
from .probes.erasure import bytes_residue, mask


def _stack(workdir: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    store = Mem0Adapter(make_memory(workdir / "mem0", os.environ.get("RIFFNEL_EMBEDDER", "hash")), agent_id="bank-bot")
    for m in json.loads((EXAMPLES / "memories.json").read_text(encoding="utf-8")):
        store.add(MemoryRecord(**m))
    sources = [Source(**s) for s in json.loads((EXAMPLES / "sources.json").read_text(encoding="utf-8"))]
    clauses = [c for s in sources for c in s.clauses]
    tests = [TestCase(**t) for t in json.loads((EXAMPLES / "tests.json").read_text(encoding="utf-8"))]
    return store, EnterpriseBankAgent(store), clauses, tests, AuditLog(workdir / "audit.db")


def run_stale(workdir: Path, log=print) -> dict:
    store, agent, clauses, tests, audit = _stack(workdir)
    by_key = {c.key: c for c in clauses}
    scope, as_of = {"product": "gold_card"}, "2026-09-01"
    inc = capture(agent, "金卡免年费需要刷几笔？", scope, "2026-08-10", "inc_real_1", "bank-bot")
    log(f"[事故] 模型={agent.model_name}\n       答：{inc.answer}\n       取用：{inc.retrieved_ids}")
    findings = investigator.investigate(inc, store, clauses)
    for f in findings:
        log(f"[调查] {f.cls} {f.memory_id}（置信度 {f.confidence}）")
    plan = corrector.make_plan(findings, store, inc.id, by_key, as_of)
    log("[修正方案预演]\n  " + "\n  ".join(corrector.diff(plan, store)))
    corrector.approve(plan, "demo-reviewer", audit)
    corrector.apply(plan, store, audit)
    rep = verifier.replay(agent, inc, clauses, as_of)
    reg = verifier.regression(agent, tests, {f.evidence["key"] for f in findings})
    log(f"[重放] {'通过' if rep['passed'] else '失败'}：{rep['answer']}")
    log(f"[回归] {'通过' if reg['passed'] else '失败'}（{len(reg['cases'])} 题）")
    ok, _ = audit.verify()
    return {"incident": inc, "findings": findings, "plan": plan, "replay": rep, "regression": reg, "audit_ok": ok,
            "passed": bool(findings) and rep["passed"] and reg["passed"] and ok}


def run_erasure(workdir: Path, log=print) -> dict:
    store, agent, clauses, tests, audit = _stack(workdir)
    scope, targets = {"user": "u_demo"}, ["13800000000"]
    needles = ["13800000000", "138 0000 0000"]
    desc, questions = "客户张三的手机号 13800000000", ["我的手机号是多少？"]

    raw = store._resolve("m_phone_raw")["id"]
    store.m.delete(raw)  # the framework's own delete: removes the live memory, leaves history rows behind
    audit.append("system", "erasure_request", "subject", "u_demo")
    pre = verifier.erasure(store, agent, scope, targets, desc, questions)
    before = bytes_residue(workdir, needles)
    log(f"[删除请求] 目标 {mask(targets[0])}；已用 Mem0 自带 delete 删除原始记录")
    log(f"[探测·修正前] L1={[i[:14] for i in pre['L1_exact']]} L2={pre['L2_variant']} L4={pre['L4_behavior']}")
    log(f"[独立字节扫描·修正前] 仍含目标的文件：{before}")

    findings = investigator.investigate_erasure(store, targets)
    plan = corrector.make_plan(findings, store, None, {}, "")
    log("[修正方案预演]\n  " + "\n  ".join(a[:90] for a in corrector.diff(plan, store)))
    corrector.approve(plan, "demo-reviewer", audit)
    corrector.apply(plan, store, audit)

    post = verifier.erasure(store, agent, scope, targets, desc, questions)
    after = bytes_residue(workdir, needles)
    log(f"[探测·修正后] {'硬性关卡均无命中' if post['passed'] else '仍有残留'}")
    log(f"[独立字节扫描·修正后] 仍含目标的文件：{after}")
    ok, _ = audit.verify()
    return {"findings": findings, "plan": plan, "pre": pre, "post": post, "bytes_before": before,
            "bytes_after": after, "audit_ok": ok,
            "passed": (not pre["clean"]) and bool(findings) and post["passed"] and not after and ok}
