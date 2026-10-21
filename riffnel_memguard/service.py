"""Workflow operations on a workspace. Used by both the CLI and the web UI."""
from __future__ import annotations

from pathlib import Path

from .adapters import memwall as memwall_io
from .agent.bank import BankAssistAgent
from .agent.command import CommandAgent
from .core import scrub
from .core.locking import atomic_write
from .core.models import Finding, Incident, Plan
from .core.workspace import Workspace
from .engines import corrector, investigator, linker, verifier
from .probes.erasure import mask
from .report.markdown import build

INCIDENT_KEYS = ("id", "occurred_at", "agent_id", "scope", "question", "answer", "retrieved_ids")


def _parse_scope(items: list[str]) -> dict:
    return dict(i.split("=", 1) for i in items)


def get_plan(st: dict, plan_id: str) -> dict:
    if plan_id not in st["plans"]:
        raise KeyError(f"unknown plan {plan_id}")
    return st["plans"][plan_id]


PLAN_FIELDS = ("actions", "status", "created_by", "approved_by", "journal")


def _as_plan(p: dict) -> Plan:
    return Plan(**{k: p[k] for k in Plan.model_fields if k in p})


def _sync(p: dict, plan: Plan) -> None:
    p.update(plan.model_dump(include=set(PLAN_FIELDS)))


def _incident(st: dict, iid: str) -> Incident:
    return Incident(**{k: v for k, v in st["incidents"][iid].items() if k in INCIDENT_KEYS})


def make_agent(w: Workspace, agent_cmd: str | None = None, timeout: float = 60.0):
    """The agent under test: an external command (see agent/command.py) or the built-in reference agent."""
    return CommandAgent(agent_cmd, timeout=timeout) if agent_cmd else BankAssistAgent(w.store)


def ask(w: Workspace, question: str, scope: dict, at: str, agent_cmd: str | None = None, timeout: float = 60.0) -> str:
    answer, retrieved = make_agent(w, agent_cmd, timeout).answer(question, scope)  # may be slow: outside the lock
    with w.transaction() as st:
        iid = f"inc_{len(st['incidents']) + 1:03d}"
        st["incidents"][iid] = Incident(id=iid, occurred_at=at, agent_id="agent-cmd" if agent_cmd else "bank-bot",
                                        scope=scope, question=question, answer=answer, retrieved_ids=retrieved).model_dump()
        if agent_cmd:  # verification replays the same agent unless told otherwise
            st["incidents"][iid]["agent_cmd"], st["incidents"][iid]["agent_timeout"] = agent_cmd, timeout
    return iid


def investigate(w: Workspace, iid: str) -> list[Finding]:
    with w.transaction() as st:
        if iid not in st["incidents"]:
            raise KeyError(f"unknown incident {iid}")
        findings = investigator.investigate(_incident(st, iid), w.store, w.clauses)
        st["incidents"][iid]["findings"] = [f.model_dump() for f in findings]
    return findings


def _register(w: Workspace, st: dict, p: Plan, fs: list[Finding], as_of: str, **extra) -> str:
    w.audit.append("system", "plan", "plan", p.id)
    st["plans"][p.id] = {**p.model_dump(), "findings": [f.model_dump() for f in fs], "as_of": as_of, **extra}
    return p.id


def plan_incident(w: Workspace, iid: str, as_of: str) -> str:
    with w.transaction() as st:
        fs = [Finding(**f) for f in st["incidents"][iid].get("findings", [])]
        if not fs:
            raise ValueError("no findings; run investigate first")
        p = corrector.make_plan(fs, w.store, iid, {c.key: c for c in w.clauses}, as_of)
        return _register(w, st, p, fs, as_of)


def revalidate(w: Workspace, as_of: str) -> tuple[list[Finding], str | None]:
    with w.transaction() as st:
        fs = investigator.revalidate(w.store, w.clauses, as_of)
        if not fs:
            return [], None
        p = corrector.make_plan(fs, w.store, None, {c.key: c for c in w.clauses}, as_of)
        return fs, _register(w, st, p, fs, as_of)


def erase(w: Workspace, subject: dict, targets: list[str], description: str) -> tuple[list[Finding], str | None]:
    """Register an erasure request and look for residue.

    The target values are kept only in secrets/<id>.json (mode 0600) until the plan has been applied and verified, then
    they are dropped. state.json holds only masked values. Nothing is stored if no residue is found.
    """
    with w.transaction() as st:
        eid = f"er_{len(st['erasures']) + 1:03d}"
        fs = investigator.investigate_erasure(w.store, targets)
        w.audit.append("system", "erasure_request", "subject", ",".join(f"{k}={v}" for k, v in subject.items()))
        st["erasures"][eid] = {"id": eid, "subject": subject, "targets_masked": [mask(t) for t in targets]}
        if not fs:
            return [], None
        w.put_secret(eid, {"targets": targets, "description": description, "subject": subject})
        p = corrector.make_plan(fs, w.store, None, {}, "")
        return fs, _register(w, st, p, fs, "", erasure_id=eid)


def erase_discard(w: Workspace, erasure_id: str) -> bool:
    """Drop the stored target values of an erasure request (e.g. instead of verifying). Returns whether there were any."""
    with w.transaction():
        dropped = w.drop_secret(erasure_id)
        if dropped:
            w.audit.append("system", "targets_discarded", "erasure", erasure_id)
        return dropped


def diff(w: Workspace, plan_id: str) -> list[str]:
    return corrector.diff(_as_plan(get_plan(w.state(), plan_id)), w.store)


def approve(w: Workspace, plan_id: str, by: str) -> None:
    with w.transaction() as st:
        p = get_plan(st, plan_id)
        obj = _as_plan(p)
        corrector.approve(obj, by, w.audit)
        _sync(p, obj)


def apply(w: Workspace, plan_id: str) -> dict:
    """Apply an approved plan (or resume a partially applied one). Returns a summary of the workspace scrub for erasures."""
    with w.transaction() as st:
        p = get_plan(st, plan_id)
        obj, store = _as_plan(p), w.store
        if obj.status == "approved":
            p["snapshot_before"] = verifier.snapshot_sha(store)

        def persist():  # after every action, so a crash or failure leaves an accurate journal
            _sync(p, obj)
            w._write_state(st)

        try:
            corrector.apply(obj, store, w.audit, on_progress=persist)
        except BaseException:
            _sync(p, obj)
            w._write_state(st)
            raise
        p["snapshot_after"] = verifier.snapshot_sha(store)
        _sync(p, obj)
        summary = {"scrubbed_strings": 0, "reports_removed": [], "targets_pending": False}
        er_id = p.get("erasure_id")
        secret = w.get_secret(er_id) if er_id else None
        if secret:
            targets = secret["targets"]
            summary["scrubbed_strings"] = scrub.scrub_state(st, targets)
            summary["reports_removed"] = scrub.scrub_reports(w.root / "reports", targets)
            summary["targets_pending"] = True
            w.audit.append("system", "scrub", "erasure", er_id,
                           f"strings={summary['scrubbed_strings']};reports={len(summary['reports_removed'])}")
            p["scrub"] = {"strings": summary["scrubbed_strings"], "reports_removed": len(summary["reports_removed"])}
        return summary


def rollback(w: Workspace, plan_id: str, by: str) -> list[str]:
    with w.transaction() as st:
        p = get_plan(st, plan_id)
        obj = _as_plan(p)
        skipped = corrector.rollback(obj, w.store, w.audit, by)
        _sync(p, obj)
        return skipped


def _erasure_secret(w: Workspace, st: dict, er_id: str) -> dict:
    """The stored target values of an erasure request; migrates workspaces that kept them in state.json."""
    secret = w.get_secret(er_id)
    legacy = st["erasures"].get(er_id, {})
    if secret is None and "targets" in legacy:
        secret = {"targets": legacy["targets"], "description": legacy.get("description", ""), "subject": legacy["subject"]}
        w.put_secret(er_id, secret)
    if secret is None:
        raise ValueError(f"the target values of {er_id} are no longer stored (they are dropped after a passed "
                         "verification or by erase-discard); register the erasure request again to verify")
    return secret


def verify(w: Workspace, plan_id: str, questions: list[str], agent_cmd: str | None = None,
           timeout: float | None = None) -> dict:
    st = w.state()  # read-only snapshot: probing may call an external agent and must not hold the workspace lock
    p = get_plan(st, plan_id)
    inc = st["incidents"].get(p.get("incident_id") or "", {})
    cmd = agent_cmd or inc.get("agent_cmd")
    agent, res = make_agent(w, cmd, timeout or inc.get("agent_timeout", 60.0)), {}
    affected = {f["evidence"]["key"] for f in p["findings"] if "key" in f["evidence"]}
    er_id = p.get("erasure_id")
    if p.get("incident_id"):
        res["replay"] = verifier.replay(agent, _incident(st, p["incident_id"]), w.clauses, p["as_of"])
        res["regression"] = verifier.regression(agent, w.tests, affected)
    elif er_id:
        secret = _erasure_secret(w, st, er_id)
        res["erasure"] = verifier.erasure(w.store, agent, secret["subject"], secret["targets"], secret["description"], questions)
    else:
        res["regression"] = verifier.regression(agent, w.tests, affected)
    with w.transaction() as st2:
        st2["verifications"][plan_id] = res
        legacy = st2["erasures"].get(er_id or "", {})
        for k in ("targets", "description"):  # a workspace from before secrets/ existed: stop keeping them in the state
            legacy.pop(k, None)
        w.audit.append("system", "verify", "plan", plan_id)
        if er_id and res.get("erasure", {}).get("passed") and w.drop_secret(er_id):
            w.audit.append("system", "targets_discarded", "erasure", er_id)
    return res


def report(w: Workspace, plan_id: str) -> Path:
    st = w.state()
    md = build(get_plan(st, plan_id), st, w.audit.events())
    out = w.root / "reports" / f"{plan_id}.md"
    out.parent.mkdir(exist_ok=True)
    atomic_write(out, md, mode=0o644)
    return out


def import_memwall(w: Workspace, report_path: Path, min_severity: str = "medium") -> tuple[list[Finding], list[str], str | None]:
    """Turn a memwall scan report into M6 findings and a quarantine plan."""
    report = memwall_io.load_report(report_path)
    fs, unmatched = memwall_io.to_findings(report, w.store, min_severity)
    if not fs:
        return [], unmatched, None
    with w.transaction() as st:
        p = corrector.make_plan(fs, w.store, None, {}, "")
        return fs, unmatched, _register(w, st, p, fs, "", source="memwall")


def export_memwall(w: Workspace, path: Path) -> int:
    return memwall_io.export_for_scan(w.store, path)


def link(w: Workspace) -> tuple[list, list]:
    links, unsupported = linker.link(w.store, w.clauses)
    with w.transaction() as st:
        st["links"] = [l.model_dump() for l in links]
    return links, unsupported


def impact(w: Workspace, version_id: str) -> dict:
    links, _ = linker.link(w.store, w.clauses)
    try:
        return linker.impact(version_id, links, w.store, w.clauses, w.tests)
    except StopIteration:
        raise KeyError(f"unknown clause version {version_id}")


def scan(w: Workspace, as_of: str) -> tuple[list[Finding], str | None]:
    """Memory health scan without an incident: M1 stale, M2 conflict, M4 unsupported."""
    links, unsupported = linker.link(w.store, w.clauses)
    m1 = linker.stale_findings(links, w.store, w.clauses, as_of)
    m2 = linker.conflict_findings(w.store, w.clauses, as_of)
    taken = {f.memory_id for f in m1 + m2}
    m4 = linker.unsupported_findings(unsupported, w.store, taken)
    fs = m1 + m2 + m4
    if not fs:
        return [], None
    with w.transaction() as st:
        p = corrector.make_plan(fs, w.store, None, {c.key: c for c in w.clauses}, as_of)
        return fs, _register(w, st, p, fs, as_of, source="scan")
