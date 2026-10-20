"""Replay, regression and erasure verification."""
from __future__ import annotations

import re
import unicodedata

from ..core.models import Clause, Incident, TestCase, sha256_text
from ..extract.rules import extract_claims
from ..probes.erasure import run_probe


def replay(agent, incident: Incident, clauses: list[Clause], as_of: str) -> dict:
    """Ask the same question again; the answer must match the version valid at `as_of`."""
    answer, retrieved = agent.answer(incident.question, incident.scope)
    by_key = {c.key: c for c in clauses}
    problems = []
    claims = extract_claims(incident.question + " " + answer, clauses)
    for c in claims:
        cur = by_key[c.key].version_at(as_of)
        if c.span in answer and cur and c.value != cur.value:
            problems.append(f"{c.key}: answered {c.value}, valid {cur.value}")
    return {"answer": answer, "retrieved": retrieved, "problems": problems, "passed": bool(claims) and not problems}


def _fold(text: str) -> str:
    """Compare answers regardless of spacing and Markdown emphasis: real models write '6 笔' or '**6笔**'."""
    return re.sub(r"[\s*_`]+", "", unicodedata.normalize("NFKC", text))


def regression(agent, cases: list[TestCase], affected_keys: set[str]) -> dict:
    """Run all test cases. Cases on affected keys must pass; the others check for collateral damage."""
    rows = []
    for t in cases:
        ans, _ = agent.answer(t.question, t.scope)
        folded = _fold(ans)
        ok = all(_fold(s) in folded for s in t.must_include) and not any(_fold(s) in folded for s in t.must_not_include)
        rows.append({"id": t.id, "key": t.key, "affected": t.key in affected_keys, "passed": ok, "answer": ans})
    return {"cases": rows, "passed": all(r["passed"] for r in rows),
            "affected": sum(r["affected"] for r in rows), "unaffected": sum(not r["affected"] for r in rows)}


def erasure(store, agent, scope, targets, description, questions) -> dict:
    res = run_probe(store, agent, scope, targets, description, questions)
    res["passed"] = res["clean"]
    return res


def snapshot_sha(store) -> str:
    return sha256_text(store.snapshot().decode("utf-8"))
