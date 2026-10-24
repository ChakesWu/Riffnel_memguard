"""Cross-lingual consistency: ask the same question in several languages and compare what the agent claims.

If a Chinese answer says 6 purchases and the Portuguese answer says 3, one of the language versions of the knowledge
is out of date. Each answer is checked against the clause version valid on the check date, and every wrong answer is
traced to the memory it came from with the same investigation used for single incidents.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from ..core.models import Clause, Finding, Incident
from ..extract.rules import extract_claims
from . import investigator


class LangResult(BaseModel):
    lang: str
    question: str
    answer: str
    retrieved_ids: list[str] = Field(default_factory=list)
    value: Any = None            # the number the answer claims, None if the answer states none
    correct: Optional[bool] = None  # vs the clause version valid on the check date; None when there is no claim


class ConsistencyResult(BaseModel):
    check_id: str
    key: str
    expected: Any = None
    results: list[LangResult]

    @property
    def values(self) -> dict[str, Any]:
        return {r.lang: r.value for r in self.results}

    @property
    def consistent(self) -> bool:
        """Every language states a number and all the numbers are equal."""
        vals = [r.value for r in self.results]
        return all(v is not None for v in vals) and len({v for v in vals}) == 1

    @property
    def all_correct(self) -> bool:
        return all(r.correct for r in self.results)

    @property
    def passed(self) -> bool:
        return self.consistent and self.all_correct

    @property
    def outliers(self) -> list[str]:
        """Languages whose claim differs from the valid value (or states none)."""
        return [r.lang for r in self.results if r.correct is not True]


def run(agent, checks: list[dict], clauses: list[Clause], as_of: str) -> list[ConsistencyResult]:
    by_key = {c.key: c for c in clauses}
    out = []
    for chk in checks:
        clause = by_key[chk["key"]]
        cur = clause.version_at(as_of)
        rows = []
        for lang, question in chk["questions"].items():
            answer, retrieved = agent.answer(question, chk["scope"])
            claim = next((c for c in extract_claims(answer, [clause]) if c.key == clause.key), None)
            value = claim.value if claim else None
            rows.append(LangResult(lang=lang, question=question, answer=answer, retrieved_ids=retrieved, value=value,
                                   correct=None if value is None or cur is None else value == cur.value))
        out.append(ConsistencyResult(check_id=chk["id"], key=clause.key, expected=cur.value if cur else None, results=rows))
    return out


def findings_for(results: list[ConsistencyResult], checks: list[dict], store, clauses: list[Clause], as_of: str) -> list[Finding]:
    """Trace every wrong or missing answer to the responsible memory (same logic as a single incident)."""
    scopes = {c["id"]: c["scope"] for c in checks}
    seen, out = set(), []
    for res in results:
        for r in res.results:
            if r.correct is not False:
                continue
            inc = Incident(id=f"{res.check_id}:{r.lang}", occurred_at=as_of, agent_id="crosslingual", scope=scopes[res.check_id],
                           question=r.question, answer=r.answer, retrieved_ids=r.retrieved_ids)
            for f in investigator.investigate(inc, store, clauses):
                if (f.cls, f.memory_id) not in seen:
                    seen.add((f.cls, f.memory_id))
                    f.evidence["language"] = r.lang
                    f.evidence["check"] = res.check_id
                    out.append(f)
    return out
