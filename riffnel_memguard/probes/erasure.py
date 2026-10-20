"""Four-layer erasure residue probe (L1 exact, L2 variant, L3 semantic, L4 behavior)."""
from __future__ import annotations

import re
import unicodedata

from ..adapters.base import similarity


def mask(value: str) -> str:
    """Mask a sensitive value for reports: keep head and tail only."""
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 7) + value[-4:]


def normalize(text: str) -> str:
    """Fold full-width characters and drop everything except letters and digits."""
    t = unicodedata.normalize("NFKC", text)
    return re.sub(r"[^0-9A-Za-z一-鿿]", "", t)


def l1_exact(records, targets):
    return [(r.id, t) for r in records for t in targets if t in r.content]


def l2_variant(records, targets):
    exact = {(i, t) for i, t in l1_exact(records, targets)}
    hits = []
    for r in records:
        n = normalize(r.content)
        for t in targets:
            if (r.id, t) not in exact and normalize(t) in n:
                hits.append((r.id, t))
    return hits


def l3_semantic(records, description, threshold=0.4):
    scores = similarity(description, [r.content for r in records])
    return [(r.id, round(s, 3)) for r, s in zip(records, scores) if s >= threshold]


def l4_behavior(agent, scope, probe_questions, targets):
    hits = []
    for q in probe_questions:
        ans, _ = agent.answer(q, scope)
        n = normalize(ans)
        if any(normalize(t) in n for t in targets):
            hits.append(q)
    return hits


def run_probe(store, agent, scope, targets, description, probe_questions) -> dict:
    """Probe every record that still exists (including invalidated ones) and the agent's behavior."""
    records = [r for r in store.list() if r.status != "deleted"]
    result = {
        "L1_exact": [i for i, _ in l1_exact(records, targets)],
        "L2_variant": [i for i, _ in l2_variant(records, targets)],
        "L3_semantic": l3_semantic(records, description),
        "L4_behavior": l4_behavior(agent, scope, probe_questions, targets),
        "targets_masked": [mask(t) for t in targets],
    }
    result["clean"] = not any(result[k] for k in ("L1_exact", "L2_variant", "L3_semantic", "L4_behavior"))
    return result
