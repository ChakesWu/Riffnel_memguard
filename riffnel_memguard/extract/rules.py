"""Rule-based claim extraction (offline, deterministic) for Chinese, Portuguese and English text.

A claim is `<number><unit>` in a text that also mentions one of the clause's keywords. Numbers may be digits (with the
Brazilian decimal comma and thousands point, or the English forms), Chinese numerals up to 999, or Portuguese and
English number words up to 99 ("seis", "vinte e três", "twenty-three").

Known limits: "1.000" is read as one thousand, never as 1.0; ordinals, fractions and ranges are not understood; Latin
keywords are matched case-insensitively as substrings.
"""
from __future__ import annotations

import re
from typing import Optional

from ..core.models import Claim, Clause, MemoryRecord

_CN = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_CN_RE = r"[零〇一二两三四五六七八九十百]+"

_UNITS_WORDS = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "três": 3, "tres": 3, "quatro": 4, "cinco": 5, "seis": 6,
    "sete": 7, "oito": 8, "nove": 9, "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14, "quatorze": 14,
    "quinze": 15, "dezesseis": 16, "dezasseis": 16, "dezessete": 17, "dezassete": 17, "dezoito": 18, "dezenove": 19,
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_TENS_WORDS = {"vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50, "sessenta": 60, "setenta": 70,
               "oitenta": 80, "noventa": 90, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
               "seventy": 70, "eighty": 80, "ninety": 90}
_ONES = "|".join(sorted((w for w, v in _UNITS_WORDS.items() if 1 <= v <= 9), key=len, reverse=True))
_TENS = "|".join(sorted(_TENS_WORDS, key=len, reverse=True))
_TEENS = "|".join(sorted((w for w, v in _UNITS_WORDS.items() if v == 0 or v >= 10), key=len, reverse=True))
# "vinte e três" / "twenty-three" / "twenty three" / "seis"
_WORDS_RE = rf"(?:(?:{_TENS})(?:(?:\s+e\s+|[\s-]+)(?:{_ONES}))?|{_TEENS}|{_ONES})"
_DIGITS_RE = r"\d{1,3}(?:[.,]\d{3})+(?![\d])|\d+(?:[.,]\d+)?"
_NUM = rf"{_DIGITS_RE}|{_CN_RE}|{_WORDS_RE}"
_NOT_LETTER = r"A-Za-zÀ-ÿ"


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


def words_to_int(s: str) -> int:
    parts = [p for p in re.split(r"\s+e\s+|[\s-]+", s.lower()) if p]
    return sum(_TENS_WORDS.get(p, _UNITS_WORDS.get(p, 0)) for p in parts)


def _num(s: str):
    t = s.strip().lower()
    if re.fullmatch(_CN_RE, t):
        return cn_to_int(t)
    if re.fullmatch(r"\d{1,3}(?:[.,]\d{3})+", t):  # 1.000 or 1,000: thousands
        return int(re.sub(r"[.,]", "", t))
    if re.fullmatch(r"\d+[.,]\d+", t):  # 2,5 or 2.5: decimals
        f = float(t.replace(",", "."))
        return int(f) if f.is_integer() else f
    if t.isdigit():
        return int(t)
    return words_to_int(t)


def _unit_re(units: list[str]) -> str:
    alts = []
    for u in sorted(units, key=len, reverse=True):
        esc = re.escape(u)
        alts.append(esc + (rf"(?![{_NOT_LETTER}])" if re.search(r"[A-Za-zÀ-ÿ]$", u) else ""))
    return "(?:" + "|".join(alts) + ")"


def extract_claim(text: str, clause: Clause) -> Optional[Claim]:
    """Find `<number><unit>` in text if the text mentions one of the clause keywords (any language)."""
    low = text.lower()
    if not any(k.lower() in low for k in clause.keywords):
        return None
    m = re.search(rf"(?<![0-9{_NOT_LETTER}])({_NUM})\s*{_unit_re(clause.units())}", text, re.IGNORECASE)
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


_PT_HINT = re.compile(r"[ãõçáéêíóúâô]|\b(?:de|do|da|dos|das|com|por|para|cartão|anuidade|isenta|isento|compras|dias)\b", re.I)


def detect_lang(text: str) -> str:
    """'zh' if the text has Chinese characters, 'pt' if it has Portuguese letters or common words, else 'en'. A heuristic:
    set MemoryRecord.lang when you know it."""
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    return "pt" if _PT_HINT.search(text) else "en"
