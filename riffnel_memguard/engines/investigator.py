"""Incident investigation and source-change revalidation."""
from __future__ import annotations

import re

from ..core.models import Clause, Finding, Incident, scope_compatible
from ..extract.rules import extract_claims, memory_claim
from ..probes.erasure import l1_exact, l2_variant, mask

INJECTION = re.compile(r"(忽略(以上|之前|先前)|无视.*指令|ignore (all )?(previous|above)|system prompt)", re.I)


from .linker import authoritative_peer, derived_closure as _derived_closure, link as _link, stale_findings  # noqa: E402


def investigate(incident: Incident, store, clauses: list[Clause]) -> list[Finding]:
    """Attribute wrong claims in an answer to retrieved memories. Empty list = not attributable to memory."""
    findings: list[Finding] = []
    claims = extract_claims(incident.question + " " + incident.answer, clauses)
    claims = [c for c in claims if c.span in incident.answer]
    by_key = {c.key: c for c in clauses}

    for claim in claims:
        clause = by_key[claim.key]
        if not scope_compatible(clause.scope, incident.scope):
            # the claim is about another scope (product/user/region): compare with the sibling clause that fits
            sib = next((c for c in clauses if c.topic and c.topic == clause.topic and c.id != clause.id
                        and scope_compatible(c.scope, incident.scope)), None)
            sv = sib.version_at(incident.occurred_at) if sib else None
            if sv is None or sv.value == claim.value:
                continue
            for mid in incident.retrieved_ids:
                rec = store.get(mid)
                mc = memory_claim(rec, clause) if rec else None
                if mc is not None and mc.value == claim.value:
                    findings.append(Finding(cls="M3", memory_id=mid, incident_id=incident.id, confidence=0.9, evidence={
                        "claim": claim.span, "memory_text": rec.content, "valid_version": sv.version,
                        "valid_value": sv.value, "valid_text": sv.text, "memory_scope": rec.scope,
                        "incident_scope": incident.scope, "target_scope": clause.scope}))
            continue
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
                "valid_text": current.text, "key": clause.key,
            }
            if old:
                findings.append(Finding(cls="M1", memory_id=mid, incident_id=incident.id, confidence=0.95,
                                        evidence={**ev, "stale_version": old[0].version}))
            else:
                peer = authoritative_peer(store, clause, rec, claim.value, incident.occurred_at)
                if peer:  # order M2 before M4: the source (via the peer memory) settles which one is right
                    findings.append(Finding(cls="M2", memory_id=mid, incident_id=incident.id, confidence=0.85,
                                            evidence={**ev, "authoritative_memory": peer}))
                else:
                    findings.append(Finding(cls="M4", memory_id=mid, incident_id=incident.id, confidence=0.6, evidence=ev))

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
    """After a source update: active memories linked to a superseded version (no incident needed)."""
    links, _ = _link(store, clauses)
    return stale_findings(links, store, clauses, as_of)
