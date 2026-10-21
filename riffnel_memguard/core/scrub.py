"""Remove erased values from Riffnel's own workspace (state file and generated reports).

Erasing data from a memory store is not enough if the tool that did it keeps a copy: incidents record the question and
the agent's answer, findings quote memories, verification results quote answers. After an erasure plan is applied,
every string in the state that contains an erased value (exactly, or after folding case, width, spacing, Chinese digits
and spelled-out '@' and '.') is replaced by a marker, and generated reports that contain it are deleted.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..probes.erasure import normalize

REDACTED = "[已遮蔽：删除请求]"
MIN_FOLDED = 4  # a folded needle shorter than this would match unrelated text


def _hits(text: str, needles: list[str]) -> bool:
    folded = None
    for n in needles:
        if n and n in text:
            return True
        nn = normalize(n)
        if len(nn) >= MIN_FOLDED:
            folded = normalize(text) if folded is None else folded
            if nn in folded:
                return True
    return False


def _scrub_inplace(obj: Any, needles: list[str]) -> int:
    """Replace matching strings inside dicts and lists, in place (so references to nested objects stay valid)."""
    count = 0
    items = obj.items() if isinstance(obj, dict) else enumerate(obj) if isinstance(obj, list) else ()
    for key, v in list(items):
        if isinstance(v, str):
            if _hits(v, needles):
                obj[key] = REDACTED
                count += 1
        elif isinstance(v, (dict, list)):
            count += _scrub_inplace(v, needles)
    return count


def scrub_state(state: dict, needles: list[str]) -> int:
    """Scrub `state` in place. Returns how many strings were replaced. Dict keys are left alone."""
    return _scrub_inplace(state, needles)


def scrub_reports(reports_dir: Path, needles: list[str]) -> list[str]:
    """Delete generated reports that still contain an erased value. Returns the deleted file names. Regenerate afterwards."""
    removed = []
    if reports_dir.is_dir():
        for f in sorted(reports_dir.glob("*.md")):
            if _hits(f.read_text(encoding="utf-8", errors="ignore"), needles):
                f.unlink()
                removed.append(f.name)
    return removed
