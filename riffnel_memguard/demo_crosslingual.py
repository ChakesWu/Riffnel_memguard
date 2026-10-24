"""Demo: one fact in three languages, one of them out of date (simulated Brazilian bank)."""
from __future__ import annotations

from pathlib import Path

from . import service
from .core.workspace import Workspace


def run(workdir: Path, log=print) -> dict:
    w = Workspace(workdir)
    w.init("bank_br")
    as_of = "2026-09-01"
    results, fs, pid = service.check_crosslingual(w, as_of)
    for r in results:
        log(f"[检查] {r.check_id}：应为 {r.expected}；" + "，".join(f"{x.lang}={x.value}" for x in r.results)
            + ("，一致" if r.consistent else "，不一致"))
    for f in fs:
        log(f"[归因] {f.cls} {f.memory_id}（{f.evidence['language']}）置信度 {f.confidence}")
    if not pid:
        return {"results": results, "findings": fs, "plan": None, "passed": False}
    log("[修正方案预演]\n  " + "\n  ".join(service.diff(w, pid)))
    service.approve(w, pid, "demo-reviewer")
    service.apply(w, pid)
    ver = service.verify(w, pid, [])
    cl = ver["crosslingual"]
    log("[复查] " + "；".join(f"{c['check_id']}：" + ("一致且正确" if c["passed"] else "仍不一致") for c in cl["checks"]))
    log(f"[回归] {'通过' if ver['regression']['passed'] else '失败'}")
    ok, _ = w.audit.verify()
    first_ok = any(not r.consistent for r in results)  # the demo is only meaningful if it started inconsistent
    return {"results": results, "findings": fs, "plan": pid, "verification": ver, "audit_ok": ok,
            "passed": first_ok and bool(fs) and cl["passed"] and ver["regression"]["passed"] and ok}
