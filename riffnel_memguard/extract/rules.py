"""Rule-based claim extraction (offline, deterministic)."""
from __future__ import annotations

import re
from typing import Optional

from ..core.models import Claim, Clause, MemoryRecord


_CN = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NUM = r"\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百]+"


def cn_to_int(s: str) -> int:
    """Chinese numerals up to 999 (e.g. 六, 十二, 二十三, 一百零五)."""
    total, cur = 0, 0
    for ch in s:
        if ch in _CN:
            cur = _CN[ch]
        elif ch == "十":
            total, cur = total + (cur or 1) * 10, 0
        elif ch == "百":
            total, cur = total + (cur or 1) * 100, 0
    return total + cur


def _num(s: str):
    if re.fullmatch(r"[零〇一二两三四五六七八九十百]+", s):
        return cn_to_int(s)
    f = float(s)
    return int(f) if f.is_integer() else f


def extract_claim(text: str, clause: Clause) -> Optional[Claim]:
    """Find `<number><unit>` in text if the text mentions one of the clause keywords."""
    if not any(k in text for k in clause.keywords):
        return None
    m = re.search(rf"({_NUM})\s*{re.escape(clause.unit)}", text)
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
