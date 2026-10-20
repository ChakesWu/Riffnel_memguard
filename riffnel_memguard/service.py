"""Workflow operations on a workspace. Used by both the CLI and the web UI."""
from __future__ import annotations

from pathlib import Path

from .adapters import memwall as memwall_io
from .agent.bank import BankAssistAgent
from .core.models import Finding, Incident, Plan
from .core.workspace import Workspace
from .engines import corrector, investigator, verifier
from .probes.erasure import mask
from .report.markdown import build

INCIDENT_KEYS = ("id", "occurred_at", "agent_id", "scope", "question", "answer", "retrieved_ids")


def _parse_scope(items: list[str]) -> dict:
    return dict(i.split("=", 1) for i in items)


def get_plan(st: dict, plan_id: str) -> dict:
    if plan_id not in st["plans"]:
        raise KeyError(f"unknown plan {plan_id}")
    return st["plans"][plan_id]


def _as_plan(p: dict) -> Plan:
    return Plan(**{k: p[k] for k in ("id", "incident_id", "actions", "status", "approved_by")})


def _sync(p: dict, plan: Plan) -> None:
    p.update(plan.model_dump(include={"actions", "status", "approved_by"}))


def _incident(st: dict, iid: str) -> Incident:
    return Incident(**{k: v for k, v in st["incidents"][iid].items() if k in INCIDENT_KEYS})


def ask(w: Workspace, question: str, scope: dict, at: str) -> str:
    answer, retrieved = BankAssistAgent(w.store).answer(question, scope)
    st = w.state()
    iid = f"inc_{len(st['incidents']) + 1:03d}"
    st["incidents"][iid] = Incident(id=iid, occurred_at=at, agent_id="bank-bot", scope=scope, question=question,
                                    answer=answer, retrieved_ids=retrieved).model_dump()
    w.save_state(st)
    return iid


def investigate(w: Workspace, iid: str) -> list[Finding]:
    st = w.state()
    findings = investigator.investigate(_incident(st, iid), w.store, w.clauses)
    st["incidents"][iid]["findings"] = [f.model_dump() for f in findings]
    w.save_state(st)
    return findings


def _register(w: Workspace, st: dict, p: Plan, fs: list[Finding], as_of: str, **extra) -> str:
    w.audit.append("system", "plan", "plan", p.id)
    st["plans"][p.id] = {**p.model_dump(), "findings": [f.model_dump() for f in fs], "as_of": as_of, **extra}
    w.save_state(st)
    return p.id


def plan_incident(w: Workspace, iid: str, as_of: str) -> str:
    st = w.state()
    fs = [Finding(**f) for f in st["incidents"][iid].get("findings", [])]
    if not fs:
        raise ValueError("no findings; run investigate first")
    p = corrector.make_plan(fs, w.store, iid, {c.key: c for c in w.clauses}, as_of)
    return _register(w, st, p, fs, as_of)


def revalidate(w: Workspace, as_of: str) -> tuple[list[Finding], str | None]:
    st = w.state()
    fs = investigator.revalidate(w.store, w.clauses, as_of)
    if not fs:
        return [], None
    p = corrector.make_plan(fs, w.store, None, {c.key: c for c in w.clauses}, as_of)
    return fs, _register(w, st, p, fs, as_of)


def erase(w: Workspace, subject: dict, targets: list[str], description: str) -> tuple[list[Finding], str | None]:
    st = w.state()
    eid = f"er_{len(st['erasures']) + 1:03d}"
    fs = investigator.investigate_erasure(w.store, targets)
    w.audit.append("system", "erasure_request", "subject", ",".join(f"{k}={v}" for k, v in subject.items()))
    st["erasures"][eid] = {"id": eid, "subject": subject, "targets": targets, "description": description,
                           "targets_masked": [mask(t) for t in targets]}
    if not fs:
        w.save_state(st)
        return [], None
    p = corrector.make_plan(fs, w.store, None, {}, "")
    return fs, _register(w, st, p, fs, "", erasure_id=eid)


def diff(w: Workspace, plan_id: str) -> list[str]:
    return corrector.diff(_as_plan(get_plan(w.state(), plan_id)), w.store)


def approve(w: Workspace, plan_id: str, by: str) -> None:
    st = w.state()
    p = get_plan(st, plan_id)
    obj = _as_plan(p)
    corrector.approve(obj, by, w.audit)
    _sync(p, obj)
    w.save_state(st)


def apply(w: Workspace, plan_id: str) -> None:
    st = w.state()
    p = get_plan(st, plan_id)
    obj, store = _as_plan(p), w.store
    p["snapshot_before"] = verifier.snapshot_sha(store)
    corrector.apply(obj, store, w.audit)  # raises PermissionError when not approved
    p["snapshot_after"] = verifier.snapshot_sha(store)
    _sync(p, obj)
    w.save_state(st)


def rollback(w: Workspace, plan_id: str, by: str) -> list[str]:
    st = w.state()
    p = get_plan(st, plan_id)
    obj = _as_plan(p)
    skipped = corrector.rollback(obj, w.store, w.audit, by)
    _sync(p, obj)
    w.save_state(st)
    return skipped


def verify(w: Workspace, plan_id: str, questions: list[str]) -> dict:
    st = w.state()
    p = get_plan(st, plan_id)
    agent, res = BankAssistAgent(w.store), {}
    affected = {f["evidence"]["key"] for f in p["findings"] if "key" in f["evidence"]}
    if p.get("incident_id"):
        res["replay"] = verifier.replay(agent, _incident(st, p["incident_id"]), w.clauses, p["as_of"])
        res["regression"] = verifier.regression(agent, w.tests, affected)
    elif p.get("erasure_id"):
        er = st["erasures"][p["erasure_id"]]
        res["erasure"] = verifier.erasure(w.store, agent, er["subject"], er["targets"], er["description"], questions)
    else:
        res["regression"] = verifier.regression(agent, w.tests, affected)
    st["verifications"][plan_id] = res
    w.save_state(st)
    w.audit.append("system", "verify", "plan", plan_id)
    return res


def report(w: Workspace, plan_id: str) -> Path:
    st = w.state()
    md = build(get_plan(st, plan_id), st, w.audit.events())
    out = w.root / "reports" / f"{plan_id}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return out


def import_memwall(w: Workspace, report_path: Path, min_severity: str = "medium") -> tuple[list[Finding], list[str], str | None]:
    """Turn a memwall scan report into M6 findings and a quarantine plan."""
    report = memwall_io.load_report(report_path)
    fs, unmatched = memwall_io.to_findings(report, w.store, min_severity)
    if not fs:
        return [], unmatched, None
    st = w.state()
    p = corrector.make_plan(fs, w.store, None, {}, "")
    return fs, unmatched, _register(w, st, p, fs, "", source="memwall")


def export_memwall(w: Workspace, path: Path) -> int:
    return memwall_io.export_for_scan(w.store, path)
