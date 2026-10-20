"""Import `memwall scan --json` reports as M6 (poisoning) findings, and export a store for scanning.

memwall (https://github.com/gbayerv26/memwall, MIT) is a separate project that scans memory stores.
Its JSON report schema is not documented in its README; this importer follows the report written by
memwall 0.6.1 (tests/fixtures/memwall_report_0.6.1.json) and rejects anything that lacks the keys it needs.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..core.models import Finding

SEVERITIES = ["info", "low", "medium", "high", "critical"]
# Heuristic confidence per memwall severity. memwall's rules are regex-based, so these stay low.
CONFIDENCE = {"info": 0.3, "low": 0.4, "medium": 0.5, "high": 0.6, "critical": 0.7}


def export_for_scan(store, path: Path) -> int:
    """Write active and quarantined records in the mem0-style shape memwall detects (`id`, `memory`)."""
    recs = [r for r in store.list() if r.status != "deleted"]
    data = [{"id": r.id, "memory": r.content, "metadata": {"scope": r.scope, "status": r.status}} for r in recs]
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(data)


def load_report(path: Path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"not valid JSON: {e}")
    if not isinstance(d, dict) or not isinstance(d.get("records"), list) or "memwall_version" not in d:
        raise ValueError("not a memwall scan report (expected keys: memwall_version, records)")
    for r in d["records"]:
        if not isinstance(r, dict) or "id" not in r or "severity" not in r or not isinstance(r.get("findings", []), list):
            raise ValueError("malformed record in memwall report (expected id, severity, findings)")
    return d


def to_findings(report: dict, store, min_severity: str = "medium") -> tuple[list[Finding], list[str]]:
    """Return (M6 findings for records present in the store, ids that could not be matched)."""
    if min_severity not in SEVERITIES:
        raise ValueError(f"min_severity must be one of {SEVERITIES}")
    floor = SEVERITIES.index(min_severity)
    by_content: dict[str, list[str]] = {}
    for r in store.list():
        by_content.setdefault(r.content, []).append(r.id)
    findings, unmatched = [], []
    for rec in report["records"]:
        sev = str(rec["severity"]).lower()
        if sev not in SEVERITIES or SEVERITIES.index(sev) < floor:
            continue
        mid: Optional[str] = rec["id"] if store.get(rec["id"]) else None
        if mid is None and len(by_content.get(rec.get("content", ""), [])) == 1:
            mid = by_content[rec["content"]][0]
        if mid is None or store.get(mid).status == "deleted":
            unmatched.append(str(rec["id"]))
            continue
        findings.append(Finding(cls="M6", memory_id=mid, confidence=CONFIDENCE[sev], evidence={
            "source": "memwall", "memwall_version": report["memwall_version"], "severity": sev,
            "rules": [f"{f.get('rule')} {f.get('name')}" for f in rec.get("findings", [])],
            "memory_text": store.get(mid).content}))
    return findings, unmatched
