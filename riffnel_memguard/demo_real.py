"""End-to-end scenarios on a real stack: a real memory framework (Mem0 or Letta) + a Pydantic AI agent.

Data is simulated (the example bank). The memory layer and the agent framework are real code paths. The language model
is the deterministic `OfflineStandIn` unless RIFFNEL_AGENT_MODEL is set. For Letta a server must already be running
(RIFFNEL_LETTA_URL, default http://localhost:8283); embeddings come from an offline stand-in unless you build the
agent yourself.
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


class _Backend:
    """The memory framework under test, plus the framework-specific steps the scenarios need."""
    label = ""
    store = None

    def upstream_delete(self, memory_id: str) -> None: ...
    def residue(self, root: Path, needles: list[str]) -> list[str] | None: ...
    def close(self) -> None: ...


class _Mem0Backend(_Backend):
    label = "Mem0"

    def __init__(self, workdir: Path):
        self.store = Mem0Adapter(make_memory(workdir / "mem0", os.environ.get("RIFFNEL_EMBEDDER", "hash")), agent_id="bank-bot")

    def upstream_delete(self, memory_id):  # the framework's own delete: removes the live memory, leaves history rows
        self.store.m.delete(self.store._resolve(memory_id)["id"])

    def residue(self, root, needles):
        return bytes_residue(root, needles)

    def close(self):
        pass


class _LettaBackend(_Backend):
    label = "Letta"

    def __init__(self, workdir: Path):
        from letta_client import Letta
        from .adapters.letta_adapter import LettaAdapter
        from .adapters.letta_testkit import create_test_agent, start_hash_embedding_server
        self.client = Letta(base_url=os.environ.get("RIFFNEL_LETTA_URL", "http://localhost:8283"), timeout=60)
        self.client.health()
        self._embed, url = start_hash_embedding_server()
        self.agent = create_test_agent(self.client, url, f"riffnel-demo-{workdir.name}")
        self.store = LettaAdapter(self.client, self.agent.id)

    def upstream_delete(self, memory_id):  # Letta deletes hard in the tested setup: only derived copies can remain
        self.store.delete(memory_id)

    def residue(self, root, needles):
        """Independent check: dump the PostgreSQL data and look for the targets. None when pg_dump is unavailable."""
        import shutil
        import subprocess
        uri = os.environ.get("RIFFNEL_LETTA_PG_URI", "postgresql://letta:letta@127.0.0.1:5432/letta")
        if not shutil.which("pg_dump"):
            return None
        proc = subprocess.run(["pg_dump", "--data-only", uri], capture_output=True, text=True, encoding="utf-8")
        if proc.returncode != 0:
            return None
        return ["postgres dump"] if any(n in proc.stdout for n in needles) else []

    def close(self):
        from .adapters.letta_testkit import delete_agent_and_archives
        try:
            delete_agent_and_archives(self.client, self.agent.id)
        finally:
            self._embed.shutdown()


def _stack(workdir: Path, backend: str = "mem0"):
    workdir.mkdir(parents=True, exist_ok=True)
    be = {"mem0": _Mem0Backend, "letta": _LettaBackend}[backend](workdir)
    for m in json.loads((EXAMPLES / "memories.json").read_text(encoding="utf-8")):
        be.store.add(MemoryRecord(**m))
    sources = [Source(**s) for s in json.loads((EXAMPLES / "sources.json").read_text(encoding="utf-8"))]
    clauses = [c for s in sources for c in s.clauses]
    tests = [TestCase(**t) for t in json.loads((EXAMPLES / "tests.json").read_text(encoding="utf-8"))]
    return be, EnterpriseBankAgent(be.store), clauses, tests, AuditLog(workdir / "audit.db")


def run_stale(workdir: Path, log=print, backend: str = "mem0") -> dict:
    be, agent, clauses, tests, audit = _stack(workdir, backend)
    try:
        return _stale(be, agent, clauses, tests, audit, log)
    finally:
        be.close()


def _stale(be, agent, clauses, tests, audit, log) -> dict:
    store = be.store
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


def run_erasure(workdir: Path, log=print, backend: str = "mem0") -> dict:
    be, agent, clauses, tests, audit = _stack(workdir, backend)
    try:
        return _erasure(be, agent, clauses, tests, audit, log, workdir)
    finally:
        be.close()


def _erasure(be, agent, clauses, tests, audit, log, workdir) -> dict:
    store = be.store
    scope, targets = {"user": "u_demo"}, ["13800000000"]
    needles = ["13800000000", "138 0000 0000"]
    desc, questions = "客户张三的手机号 13800000000", ["我的手机号是多少？"]

    be.upstream_delete("m_phone_raw")
    audit.append("system", "erasure_request", "subject", "u_demo")
    pre = verifier.erasure(store, agent, scope, targets, desc, questions)
    before = be.residue(workdir, needles)
    log(f"[删除请求] 目标 {mask(targets[0])}；已用 {be.label} 删除原始记录")
    log(f"[探测·修正前] L1={[i[:14] for i in pre['L1_exact']]} L2={pre['L2_variant']} L4={pre['L4_behavior']}")
    log(f"[独立扫描·修正前] 仍含目标：{'未检查（无 pg_dump）' if before is None else before}")

    findings = investigator.investigate_erasure(store, targets)
    plan = corrector.make_plan(findings, store, None, {}, "")
    log("[修正方案预演]\n  " + "\n  ".join(a[:90] for a in corrector.diff(plan, store)))
    corrector.approve(plan, "demo-reviewer", audit)
    corrector.apply(plan, store, audit)

    post = verifier.erasure(store, agent, scope, targets, desc, questions)
    after = be.residue(workdir, needles)
    log(f"[探测·修正后] {'硬性关卡均无命中' if post['passed'] else '仍有残留'}")
    log(f"[独立扫描·修正后] 仍含目标：{'未检查（无 pg_dump）' if after is None else after}")
    ok, _ = audit.verify()
    return {"findings": findings, "plan": plan, "pre": pre, "post": post, "bytes_before": before,
            "bytes_after": after, "audit_ok": ok,
            "passed": (not pre["clean"]) and bool(findings) and post["passed"] and not (after or []) and ok}
