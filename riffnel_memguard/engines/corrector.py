"""Build, preview, approve, apply and roll back correction plans."""
from __future__ import annotations

import getpass
import os
import uuid
from datetime import datetime, timezone

from ..core.audit import AuditLog
from ..core.models import Action, Finding, MemoryRecord, Plan, sha256_json
from ..core.models import scope_compatible  # noqa: F401
from ..extract.rules import memory_claim
from .linker import derived_closure as _derived_closure


def _id(prefix: str, seed: str) -> str:
    return f"{prefix}_{uuid.uuid5(uuid.NAMESPACE_URL, seed).hex[:8]}"


def make_plan(findings: list[Finding], store, incident_id: str | None, clauses_by_key: dict, as_of: str) -> Plan:
    actions: list[Action] = []
    seen: set[tuple] = set()

    def add(a: Action):
        # an invalidate and a purge_derived(mode=invalidate) on the same memory are one change
        deactivate = a.type == "invalidate" or (a.type == "purge_derived" and a.payload.get("mode") == "invalidate")
        k = ("deactivate" if deactivate else a.type, a.target)
        if k not in seen:
            seen.add(k)
            actions.append(a)

    for f in findings:
        rec = store.get(f.memory_id)
        if rec is None:
            continue
        derived = sorted(_derived_closure(store, {f.memory_id}))
        if f.cls == "M1":
            clause = clauses_by_key[f.evidence["key"]]
            cur = clause.version_at(as_of)
            add(Action(type="invalidate", target=rec.id, payload={"reason": f"superseded by {cur.version}"}))
            exists = any(r.status == "active" and r.id != rec.id and r.scope == rec.scope
                         and (mc := memory_claim(r, clause)) is not None and mc.value == cur.value
                         for r in store.list())
            planned = any(x.type == "add" and x.payload["record"]["key"] == clause.key
                          and x.payload["record"]["scope"] == rec.scope for x in actions)
            # only facts get a replacement: a stale summary is retired, not re-created
            if not exists and not planned and rec.kind == "fact":
                new = MemoryRecord(id=_id("mem", rec.id + cur.id), content=cur.text, kind="fact", scope=rec.scope,
                                   key=clause.key, value=cur.value, written_at=as_of, supersedes=rec.id)
                add(Action(type="add", target=new.id, payload={"record": new.model_dump()}))
            for d in derived:
                add(Action(type="purge_derived", target=d, payload={"mode": "invalidate"}))
        elif f.cls == "M3":
            add(Action(type="rescope", target=rec.id, payload={
                "scope": f.evidence["target_scope"], "previous_scope": rec.scope}))
        elif f.cls == "M2":
            if f.evidence.get("authoritative_memory"):
                add(Action(type="invalidate", target=rec.id, payload={
                    "reason": f"conflicts with {f.evidence['authoritative_memory']}, which matches the source"}))
                for d in derived:
                    add(Action(type="purge_derived", target=d, payload={"mode": "invalidate"}))
            else:  # the source cannot pick a winner: hold for human review
                add(Action(type="quarantine", target=rec.id, payload={"reason": "M2: no memory matches the source"}))
        elif f.cls in ("M4", "M6"):
            add(Action(type="quarantine", target=rec.id, payload={"reason": f.cls}))
        elif f.cls == "M5":
            add(Action(type="delete", target=rec.id))
            for d in derived:
                add(Action(type="purge_derived", target=d, payload={"mode": "delete"}))
    for a in actions:
        if a.target and (r := store.get(a.target)):
            a.before_sha256 = r.sha()
    pid = _id("plan", sha256_json([a.model_dump() for a in actions]))
    return Plan(id=pid, incident_id=incident_id, actions=actions, created_by=current_actor())


def diff(plan: Plan, store) -> list[str]:
    """Dry run: describe what would change, without touching the store."""
    lines = []
    for a in plan.actions:
        r = store.get(a.target) if a.target else None
        text = (r.content[:40] + "…") if r else ""
        if a.type == "add":
            lines.append(f"+ add {a.target}: {a.payload['record']['content']}")
        else:
            lines.append(f"- {a.type} {a.target} {text}")
    return lines


def current_actor() -> str:
    """Who is running the command: RIFFNEL_USER, else the operating-system account."""
    try:
        return os.environ.get("RIFFNEL_USER") or getpass.getuser()
    except Exception:
        return "unknown"


def check_approver(by: str, created_by: str | None) -> None:
    """Approver policy. This is a local-trust control, not authentication: the name is whatever the caller types.

    RIFFNEL_APPROVERS=alice,bob  only these names may approve.
    RIFFNEL_FOUR_EYES=1          the person who drafted the plan may not approve it (compared by name).
    """
    if not by or not by.strip():
        raise PermissionError("an approver name is required")
    allowed = {n.strip() for n in os.environ.get("RIFFNEL_APPROVERS", "").split(",") if n.strip()}
    if allowed and by not in allowed:
        raise PermissionError(f"{by!r} is not in RIFFNEL_APPROVERS")
    if os.environ.get("RIFFNEL_FOUR_EYES") == "1" and created_by and by == created_by:
        raise PermissionError("four-eyes rule: the person who drafted the plan cannot approve it")


def approve(plan: Plan, by: str, audit: AuditLog) -> None:
    if plan.status not in ("draft", "rolled_back"):
        raise PermissionError(f"plan is {plan.status}; only a draft or rolled-back plan can be approved")
    check_approver(by, plan.created_by)
    plan.status, plan.approved_by = "approved", by
    audit.append(by, "approve", "plan", plan.id,
                 sha256_json({"actions": [a.model_dump(exclude={"after_sha256"}) for a in plan.actions], "os_user": current_actor()}))


def _run(a: Action, store) -> None:
    if a.type == "invalidate":
        store.invalidate(a.target, a.payload.get("reason", ""))
    elif a.type == "quarantine":
        store.quarantine(a.target, a.payload.get("reason", ""))
    elif a.type == "add":
        if store.get(a.target) is None:  # idempotent: a resumed apply must not add twice
            store.add(MemoryRecord(**a.payload["record"]))
    elif a.type == "delete":
        store.delete(a.target)
    elif a.type == "purge_derived":
        if a.payload.get("mode") == "delete":
            store.delete(a.target)
        else:
            store.invalidate(a.target, "derived purge")
    elif a.type == "rescope":
        store.rescope(a.target, a.payload["scope"])
    # "advice" changes nothing


def apply(plan: Plan, store, audit: AuditLog, on_progress=None) -> None:
    """Carry out the plan one action at a time, keeping a journal.

    This is NOT a transaction: stores offer none across several memories. If an action fails, the plan becomes
    `apply_failed` with the journal of what was done; calling apply again resumes after the last completed action
    (every action is idempotent), and rollback undoes only what the journal lists. `on_progress` is called after
    every change so the caller can persist the plan.
    """
    if plan.status not in ("approved", "apply_failed"):
        raise PermissionError(f"plan is {plan.status}; only an approved (or partially applied) plan can be applied")
    done = set(plan.journal)
    for i, a in enumerate(plan.actions):
        if i in done:
            continue
        try:
            _run(a, store)
        except Exception as e:
            plan.status = "apply_failed"
            audit.append(plan.approved_by or "system", f"apply_failed:{a.type}", "memory", a.target or "", type(e).__name__)
            if on_progress:
                on_progress()
            raise
        r = store.get(a.target) if a.target else None
        a.after_sha256 = r.sha() if r else None
        # the audit log stores ids and hashes only, never memory content
        audit.append(plan.approved_by or "system", f"apply:{a.type}", "memory", a.target or "", a.after_sha256 or "")
        plan.journal.append(i)
        if on_progress:
            on_progress()
    plan.status = "applied"
    if on_progress:
        on_progress()


def rollback(plan: Plan, store, audit: AuditLog, by: str) -> list[str]:
    """Undo invalidate/quarantine/add/rescope for the actions that were carried out. Deletes cannot be undone."""
    if plan.status not in ("applied", "apply_failed"):
        raise PermissionError(f"plan is {plan.status}; only an applied or partially applied plan can be rolled back")
    done = sorted(plan.journal) or (list(range(len(plan.actions))) if plan.status == "applied" else [])  # old plans: no journal
    skipped = []
    for i in reversed(done):
        a = plan.actions[i]
        if a.type in ("invalidate", "quarantine") or (a.type == "purge_derived" and a.payload.get("mode") == "invalidate"):
            store.restore(a.target)
        elif a.type == "add":
            store.delete(a.target)
        elif a.type == "rescope":
            store.rescope(a.target, a.payload["previous_scope"])
        elif a.type in ("delete", "purge_derived"):
            skipped.append(a.target)
        audit.append(by, f"rollback:{a.type}", "memory", a.target or "")
    plan.journal = []
    plan.status = "rolled_back"
    return skipped
