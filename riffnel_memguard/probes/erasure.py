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


_CN_DIGITS = str.maketrans("零〇一二三四五六七八九", "00123456789")
_AT = re.compile(r"\s*(?:\[at\]|\(at\)|\bat\b)\s*", re.I)
_DOT = re.compile(r"\s*(?:\[dot\]|\(dot\)|\bdot\b)\s*", re.I)


def normalize(text: str) -> str:
    """Fold full-width characters, Chinese digits and spelled-out '@' / '.', then keep letters and digits only."""
    t = unicodedata.normalize("NFKC", text).translate(_CN_DIGITS)
    t = _DOT.sub(".", _AT.sub("@", t))
    return re.sub(r"[^0-9A-Za-z一-鿿]", "", t).lower()


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


def traces_of(store) -> list:
    """Records a store keeps outside its live memories (e.g. Mem0 history rows). Optional adapter method."""
    return store.traces() if hasattr(store, "traces") else []


def run_probe(store, agent, scope, targets, description, probe_questions) -> dict:
    """Probe every record that still exists (including invalidated ones) and the agent's behavior."""
    records = [r for r in store.list() if r.status != "deleted"]
    scanned = records + traces_of(store)
    result = {
        "L1_exact": [i for i, _ in l1_exact(scanned, targets)],
        "L2_variant": [i for i, _ in l2_variant(scanned, targets)],
        "L3_semantic": l3_semantic(records, description),
        "L4_behavior": l4_behavior(agent, scope, probe_questions, targets),
        "targets_masked": [mask(t) for t in targets],
    }
    # L1, L2 and L4 are hard gates. L3 (semantic similarity) is advisory: it flagged unrelated look-alike
    # records in the benchmark, so a hit asks for human review instead of failing the probe on its own.
    result["clean"] = not any(result[k] for k in ("L1_exact", "L2_variant", "L4_behavior"))
    result["needs_review"] = bool(result["L3_semantic"])
    return result
