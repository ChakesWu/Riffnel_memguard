"""Provenance linking, impact analysis and conflict detection."""
from __future__ import annotations

from ..adapters.base import similarity
from ..core.models import Clause, ClauseVersion, Finding, ProvenanceLink, scope_compatible
from ..extract.rules import memory_claim

# Default minimum text similarity for a semantic link. 0.2 is an unvalidated starting value:
# paraphrased summaries in the simulated data score about 0.26-0.28 (see tests/test_linker.py).
SEMANTIC_THRESHOLD = 0.2


def _pick(versions: list[ClauseVersion], written_at: str) -> ClauseVersion:
    """Among versions with the same value, prefer the one valid when the memory was written."""
    for v in versions:
        if written_at and v.valid_from <= written_at and (v.valid_to is None or written_at <= v.valid_to):
            return v
    return versions[0]


def link(store, clauses: list[Clause], threshold: float = SEMANTIC_THRESHOLD):
    """Link memories to the clause version they rely on.

    Returns (links, unsupported). `unsupported` lists (memory_id, clause_key, value, reason) for memories
    that state a rule value no version carries, or that match only weakly: candidates for M4.
    """
    by_vid = {v.id: (c, v) for c in clauses for v in c.versions}
    links: list[ProvenanceLink] = []
    unsupported: list[tuple] = []
    for rec in store.list():
        if rec.status == "deleted":
            continue
        if rec.source_ref in by_vid:
            links.append(ProvenanceLink(memory_id=rec.id, clause_version_id=rec.source_ref, method="explicit", confidence=1.0))
            continue
        for clause in clauses:
            claim = memory_claim(rec, clause)
            if claim is None:
                continue
            same = [v for v in clause.versions if v.value == claim.value]
            if not same:
                unsupported.append((rec.id, clause.key, claim.value, "value_matches_no_version"))
                continue
            v = _pick(same, rec.written_at)
            if rec.key == clause.key:
                links.append(ProvenanceLink(memory_id=rec.id, clause_version_id=v.id, method="key_match", confidence=0.9))
                continue
            sim = round(similarity(rec.content, [v.text])[0], 3)
            if sim >= threshold:
                links.append(ProvenanceLink(memory_id=rec.id, clause_version_id=v.id, method="semantic", confidence=sim))
            else:
                unsupported.append((rec.id, clause.key, claim.value, f"low_similarity:{sim}"))
    return links, unsupported


def derived_closure(store, root_ids: set[str]) -> set[str]:
    out, frontier = set(), set(root_ids)
    while frontier:
        nxt = {r.id for r in store.list() if set(r.derived_from) & frontier} - out
        out |= nxt
        frontier = nxt
    return out


def impact(version_id: str, links: list[ProvenanceLink], store, clauses: list[Clause], tests) -> dict:
    """clause version -> memories -> derived memories -> test cases (the graph in ARCHITECTURE 8.4)."""
    clause = next(c for c in clauses if any(v.id == version_id for v in c.versions))
    mems = sorted({l.memory_id for l in links if l.clause_version_id == version_id})
    derived = sorted(derived_closure(store, set(mems)) - set(mems))
    return {"clause_key": clause.key, "memories": mems, "derived": derived,
            "tests": sorted(t.id for t in tests if t.key == clause.key)}


def stale_findings(links, store, clauses, as_of: str) -> list[Finding]:
    """M1 without an incident: active memories linked to a version that was superseded before `as_of`."""
    by_vid = {v.id: (c, v) for c in clauses for v in c.versions}
    out = []
    for l in links:
        clause, v = by_vid[l.clause_version_id]
        rec, cur = store.get(l.memory_id), clause.version_at(as_of)
        if rec is None or rec.status != "active" or cur is None or not scope_compatible(rec.scope, clause.scope):
            continue
        if v.valid_to is not None and v.valid_to < as_of and v.value != cur.value:
            out.append(Finding(cls="M1", memory_id=rec.id, confidence=l.confidence, evidence={
                "key": clause.key, "memory_text": rec.content, "stale_version": v.version,
                "valid_version": cur.version, "valid_value": cur.value, "valid_text": cur.text,
                "trigger": "source_update", "link_method": l.method}))
    return out


def authoritative_peer(store, clause: Clause, rec, value, as_of: str):
    """An active memory with the same scope that carries the value valid at `as_of`, if any."""
    cur = clause.version_at(as_of)
    if cur is None:
        return None
    for r in store.list():
        if r.id != rec.id and r.status == "active" and r.scope == rec.scope:
            mc = memory_claim(r, clause)
            if mc is not None and mc.value == cur.value:
                return r.id
    return None


def conflict_findings(store, clauses: list[Clause], as_of: str) -> list[Finding]:
    """M2: same key and scope, several active memories with different values, the loser not explained by M1."""
    out = []
    for clause in clauses:
        cur = clause.version_at(as_of)
        if cur is None:
            continue
        stale_values = {v.value for v in clause.superseded_at(as_of)}
        groups: dict[tuple, list] = {}
        for r in store.list():
            if r.status != "active":
                continue
            mc = memory_claim(r, clause)
            if mc is not None:
                groups.setdefault(tuple(sorted(r.scope.items())), []).append((r, mc.value))
        for members in groups.values():
            if len({v for _, v in members}) < 2:
                continue
            keeper = next((r.id for r, v in members if v == cur.value), None)
            for r, v in members:
                if v == cur.value or v in stale_values:
                    continue
                out.append(Finding(cls="M2", memory_id=r.id, confidence=0.85 if keeper else 0.6, evidence={
                    "key": clause.key, "memory_text": r.content, "authoritative_memory": keeper,
                    "valid_version": cur.version, "valid_value": cur.value, "valid_text": cur.text}))
    return out


def unsupported_findings(unsupported, store, exclude: set[str]) -> list[Finding]:
    out = []
    for mid, key, value, reason in unsupported:
        rec = store.get(mid)
        if rec is None or rec.status != "active" or mid in exclude:
            continue
        out.append(Finding(cls="M4", memory_id=mid, confidence=0.6,
                           evidence={"key": key, "memory_text": rec.content, "reason": reason}))
    return out
