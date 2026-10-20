"""Rule-based claim extraction (offline, deterministic)."""
from __future__ import annotations

import re
from typing import Optional

from ..core.models import Claim, Clause, MemoryRecord


def _num(s: str):
    f = float(s)
    return int(f) if f.is_integer() else f


def extract_claim(text: str, clause: Clause) -> Optional[Claim]:
    """Find `<number><unit>` in text if the text mentions one of the clause keywords."""
    if not any(k in text for k in clause.keywords):
        return None
    m = re.search(rf"(\d+(?:\.\d+)?)\s*{re.escape(clause.unit)}", text)
    if not m:
        return None
    return Claim(key=clause.key, value=_num(m.group(1)), span=m.group(0))


def extract_claims(text: str, clauses: list[Clause]) -> list[Claim]:
    return [c for c in (extract_claim(text, cl) for cl in clauses) if c]


def memory_claim(rec: MemoryRecord, clause: Clause) -> Optional[Claim]:
    """Value of a memory for a clause: explicit key/value first, text extraction as fallback."""
    if rec.key == clause.key and rec.value is not None:
        return Claim(key=clause.key, value=rec.value, span=str(rec.value))
    return extract_claim(rec.content, clause)
