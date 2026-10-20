"""Incident investigation and source-change revalidation."""
from __future__ import annotations

import re

from ..core.models import Clause, Finding, Incident, scope_compatible
from ..extract.rules import extract_claims, memory_claim
from ..probes.erasure import l1_exact, l2_variant, mask

INJECTION = re.compile(r"(忽略(以上|之前|先前)|无视.*指令|ignore (all )?(previous|above)|system prompt)", re.I)


def _derived_closure(store, root_ids: set[str]) -> set[str]:
    out, frontier = set(), set(root_ids)
    while frontier:
        nxt = {r.id for r in store.list() if set(r.derived_from) & frontier} - out
        out |= nxt
        frontier = nxt
    return out


def investigate(incident: Incident, store, clauses: list[Clause]) -> list[Finding]:
    """Attribute wrong claims in an answer to retrieved memories. Empty list = not attributable to memory."""
    findings: list[Finding] = []
    claims = extract_claims(incident.question + " " + incident.answer, clauses)
    claims = [c for c in claims if c.span in incident.answer]
    by_key = {c.key: c for c in clauses}

    for claim in claims:
        clause = by_key[claim.key]
        current = clause.version_at(incident.occurred_at)
        if current is None or claim.value == current.value:
            continue
        for mid in incident.retrieved_ids:
            rec = store.get(mid)
            if rec is None:
                continue
            mc = memory_claim(rec, clause)
            if mc is None or mc.value != claim.value:
                continue
            old = [v for v in clause.superseded_at(incident.occurred_at) if v.value == claim.value]
            ev = {
                "claim": claim.span, "memory_text": rec.content,
                "valid_version": current.version, "valid_value": current.value,
                "valid_text": current.text,
            }
            if not scope_compatible(rec.scope, incident.scope) or (
                rec.scope and any(k not in incident.scope for k in rec.scope)
            ):
                findings.append(Finding(cls="M3", memory_id=mid, incident_id=incident.id, confidence=0.9,
                                        evidence={**ev, "memory_scope": rec.scope, "incident_scope": incident.scope}))
            elif old:
                findings.append(Finding(cls="M1", memory_id=mid, incident_id=incident.id, confidence=0.95,
                                        evidence={**ev, "stale_version": old[0].version, "key": clause.key}))
            else:
                findings.append(Finding(cls="M4", memory_id=mid, incident_id=incident.id, confidence=0.6,
                                        evidence={**ev, "key": clause.key}))

    for mid in incident.retrieved_ids:
        rec = store.get(mid)
        if rec and INJECTION.search(rec.content):
            findings.append(Finding(cls="M6", memory_id=mid, incident_id=incident.id, confidence=0.5,
                                    evidence={"reason": "instruction-like text (heuristic)"}))
    return findings


def investigate_erasure(store, targets: list[str]) -> list[Finding]:
    """Find residue of erased values in remaining records (raw or derived)."""
    records = [r for r in store.list() if r.status != "deleted"]
    hits = {i: "exact" for i, _ in l1_exact(records, targets)}
    hits.update({i: "variant" for i, _ in l2_variant(records, targets) if i not in hits})
    return [
        Finding(cls="M5", memory_id=i, confidence=1.0 if how == "exact" else 0.9,
                evidence={"match": how, "targets_masked": [mask(t) for t in targets]})
        for i, how in sorted(hits.items())
    ]


def revalidate(store, clauses: list[Clause], as_of: str) -> list[Finding]:
    """After a source update: active memories still holding a superseded value (no incident needed)."""
    findings = []
    for clause in clauses:
        current = clause.version_at(as_of)
        if current is None:
            continue
        stale_values = {v.value: v for v in clause.superseded_at(as_of)}
        for rec in store.list():
            if rec.status != "active" or not scope_compatible(rec.scope, clause.scope):
                continue
            mc = memory_claim(rec, clause)
            if mc and mc.value != current.value and mc.value in stale_values:
                findings.append(Finding(cls="M1", memory_id=rec.id, confidence=0.9, evidence={
                    "key": clause.key, "memory_text": rec.content, "stale_version": stale_values[mc.value].version,
                    "valid_version": current.version, "valid_value": current.value, "valid_text": current.text,
                    "trigger": "source_update"}))
    return findings
