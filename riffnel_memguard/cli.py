"""Command line entry point."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import typer

from . import demo as demo_mod
from .agent.bank import BankAssistAgent
from .core.audit import AuditLog
from .core.models import Incident, Plan
from .core.workspace import Workspace
from .engines import corrector, investigator, verifier
from .report.markdown import build, mask_text

app = typer.Typer(help="Riffnel_memguard: memory error investigation and correction verification.")
audit_app = typer.Typer(help="Audit log commands.")
app.add_typer(audit_app, name="audit")

WS_OPT = typer.Option(Path(os.environ.get("RIFFNEL_WS", ".riffnel")), "--ws", help="Workspace directory")


def _scope(items: list[str]) -> dict:
    return dict(i.split("=", 1) for i in items)


def _plan(st: dict, plan_id: str) -> dict:
    if plan_id not in st["plans"]:
        raise typer.BadParameter(f"unknown plan {plan_id}")
    return st["plans"][plan_id]


def _as_plan(p: dict) -> Plan:
    return Plan(**{k: p[k] for k in ("id", "incident_id", "actions", "status", "approved_by")})


def _sync(p: dict, plan: Plan) -> None:
    p.update(plan.model_dump(include={"actions", "status", "approved_by"}))


@app.command()
def init(ws: Path = WS_OPT, example: bool = typer.Option(True, help="Copy the simulated bank example")):
    """Create a workspace (with the simulated bank example by default)."""
    Workspace(ws).init(example)
    typer.echo(f"已初始化 {ws}")


@app.command()
def ask(question: str, scope: list[str] = typer.Option(..., "--scope", help="key=value, repeatable"),
        at: str = typer.Option(..., help="Incident date, YYYY-MM-DD"), ws: Path = WS_OPT):
    """Ask the reference agent and record the exchange as an incident."""
    w, sc = Workspace(ws), _scope(scope)
    answer, retrieved = BankAssistAgent(w.store).answer(question, sc)
    st = w.state()
    iid = f"inc_{len(st['incidents']) + 1:03d}"
    st["incidents"][iid] = Incident(id=iid, occurred_at=at, agent_id="bank-bot", scope=sc, question=question,
                                    answer=answer, retrieved_ids=retrieved).model_dump()
    w.save_state(st)
    typer.echo(f"{iid}\n答：{answer}")


@app.command()
def investigate(incident_id: str, ws: Path = WS_OPT):
    """Find the memories responsible for a wrong answer."""
    w, st = Workspace(ws), Workspace(ws).state()
    inc = Incident(**st["incidents"][incident_id])
    findings = investigator.investigate(inc, w.store, w.clauses)
    st["incidents"][incident_id]["findings"] = [f.model_dump() for f in findings]
    w.save_state(st)
    if not findings:
        typer.echo("无法归因：错误不来自被取用的记忆（请检查提示词或模型层）。")
    for f in findings:
        typer.echo(f"{f.cls} {f.memory_id} 置信度 {f.confidence}：{mask_text(f.evidence.get('memory_text', ''))}")


@app.command()
def plan(incident_id: str, as_of: str = typer.Option(..., help="Date the correction should be valid at"),
         ws: Path = WS_OPT):
    """Draft a correction plan from an incident's findings."""
    from .core.models import Finding
    w, st = Workspace(ws), Workspace(ws).state()
    fs = [Finding(**f) for f in st["incidents"][incident_id].get("findings", [])]
    if not fs:
        raise typer.BadParameter("no findings; run investigate first")
    p = corrector.make_plan(fs, w.store, incident_id, {c.key: c for c in w.clauses}, as_of)
    w.audit.append("system", "plan", "plan", p.id)
    st["plans"][p.id] = {**p.model_dump(), "findings": [f.model_dump() for f in fs], "as_of": as_of}
    w.save_state(st)
    typer.echo(p.id)


@app.command()
def revalidate(as_of: str = typer.Option(...), ws: Path = WS_OPT):
    """After a source update: find active memories that still hold a superseded value."""
    w, st = Workspace(ws), Workspace(ws).state()
    fs = investigator.revalidate(w.store, w.clauses, as_of)
    if not fs:
        typer.echo("没有依赖旧版本的有效记忆。")
        return
    p = corrector.make_plan(fs, w.store, None, {c.key: c for c in w.clauses}, as_of)
    w.audit.append("system", "plan", "plan", p.id)
    st["plans"][p.id] = {**p.model_dump(), "findings": [f.model_dump() for f in fs], "as_of": as_of}
    w.save_state(st)
    typer.echo(f"{len(fs)} 条记忆过期，方案 {p.id}")


@app.command()
def erase(subject: list[str] = typer.Option(..., "--subject", help="key=value scope of the data subject"),
          target: list[str] = typer.Option(..., "--target", help="Exact value that must be gone, repeatable"),
          description: str = typer.Option("", help="Text used for the semantic probe"),
          ws: Path = WS_OPT):
    """Register an erasure request, look for residue, and draft a plan."""
    from .probes.erasure import mask
    w, st = Workspace(ws), Workspace(ws).state()
    eid = f"er_{len(st['erasures']) + 1:03d}"
    fs = investigator.investigate_erasure(w.store, target)
    w.audit.append("system", "erasure_request", "subject", ",".join(subject))
    st["erasures"][eid] = {"id": eid, "subject": _scope(subject), "targets": target, "description": description,
                           "targets_masked": [mask(t) for t in target]}
    if not fs:
        w.save_state(st)
        typer.echo("未发现残留。")
        return
    p = corrector.make_plan(fs, w.store, None, {}, "")
    w.audit.append("system", "plan", "plan", p.id)
    st["plans"][p.id] = {**p.model_dump(), "findings": [f.model_dump() for f in fs], "as_of": "", "erasure_id": eid}
    w.save_state(st)
    typer.echo(f"发现 {len(fs)} 处残留，方案 {p.id}")


@app.command("simulate-delete")
def simulate_delete(memory_id: str, ws: Path = WS_OPT):
    """Delete one record directly, imitating an upstream deletion that missed derived copies."""
    w = Workspace(ws)
    w.store.delete(memory_id)
    w.audit.append("system", "upstream_delete", "memory", memory_id)
    typer.echo(f"已删除 {memory_id}")


@app.command()
def diff(plan_id: str, ws: Path = WS_OPT):
    """Dry run: show what the plan would change."""
    w, st = Workspace(ws), Workspace(ws).state()
    for line in corrector.diff(_as_plan(_plan(st, plan_id)), w.store):
        typer.echo(mask_text(line))


@app.command()
def approve(plan_id: str, by: str = typer.Option(...), ws: Path = WS_OPT):
    w, st = Workspace(ws), Workspace(ws).state()
    p = _plan(st, plan_id)
    obj = _as_plan(p)
    corrector.approve(obj, by, w.audit)
    _sync(p, obj)
    w.save_state(st)
    typer.echo(f"{plan_id} 已由 {by} 审批")


@app.command()
def apply(plan_id: str, ws: Path = WS_OPT):
    w, st = Workspace(ws), Workspace(ws).state()
    p = _plan(st, plan_id)
    obj = _as_plan(p)
    store = w.store
    p["snapshot_before"] = verifier.snapshot_sha(store)
    try:
        corrector.apply(obj, store, w.audit)
    except PermissionError as e:
        raise typer.BadParameter(str(e))
    p["snapshot_after"] = verifier.snapshot_sha(store)
    _sync(p, obj)
    w.save_state(st)
    typer.echo(f"{plan_id} 已应用")


@app.command()
def rollback(plan_id: str, by: str = typer.Option(...), ws: Path = WS_OPT):
    w, st = Workspace(ws), Workspace(ws).state()
    p = _plan(st, plan_id)
    obj = _as_plan(p)
    skipped = corrector.rollback(obj, w.store, w.audit, by)
    _sync(p, obj)
    w.save_state(st)
    typer.echo(f"已回滚；无法回滚的删除：{skipped}" if skipped else "已回滚")


@app.command()
def verify(plan_id: str, question: list[str] = typer.Option(["我的手机号是多少？"], "--question"), ws: Path = WS_OPT):
    """Run replay + regression (incident plans) or the four-layer probe (erasure plans)."""
    w, st = Workspace(ws), Workspace(ws).state()
    p = _plan(st, plan_id)
    agent, res = BankAssistAgent(w.store), {}
    if p.get("incident_id"):
        inc = Incident(**{k: v for k, v in st["incidents"][p["incident_id"]].items() if k != "findings"})
        res["replay"] = verifier.replay(agent, inc, w.clauses, p["as_of"])
        res["regression"] = verifier.regression(agent, w.tests, {f["evidence"]["key"] for f in p["findings"] if "key" in f["evidence"]})
    elif p.get("erasure_id"):
        er = st["erasures"][p["erasure_id"]]
        res["erasure"] = verifier.erasure(w.store, agent, er["subject"], er["targets"], er["description"], question)
    else:
        affected = {f["evidence"]["key"] for f in p["findings"] if "key" in f["evidence"]}
        res["regression"] = verifier.regression(agent, w.tests, affected)
    st["verifications"][plan_id] = res
    w.save_state(st)
    w.audit.append("system", "verify", "plan", plan_id)
    for k, v in res.items():
        typer.echo(f"{k}: {'通过' if v['passed'] else '失败'}")
    raise typer.Exit(0 if all(v["passed"] for v in res.values()) else 1)


@app.command()
def report(plan_id: str, ws: Path = WS_OPT):
    """Write the Markdown evidence report."""
    w, st = Workspace(ws), Workspace(ws).state()
    md = build(_plan(st, plan_id), st, w.audit.events())
    out = Path(ws) / "reports" / f"{plan_id}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(md, encoding="utf-8")
    typer.echo(str(out))


@app.command()
def demo(scenario: str = typer.Argument(..., help="stale | erasure"),
         workdir: Path = typer.Option(None, help="Where to write working files (default: temp dir)")):
    """Run a full offline demo on simulated data."""
    runner = {"stale": demo_mod.run_stale, "erasure": demo_mod.run_erasure}.get(scenario)
    if runner is None:
        raise typer.BadParameter("scenario must be 'stale' or 'erasure'")
    wd = workdir or Path(tempfile.mkdtemp(prefix="riffnel_"))
    result = runner(wd)
    typer.echo(f"\n结果：{'通过' if result['passed'] else '失败'}（工作目录 {wd}）")
    raise typer.Exit(0 if result["passed"] else 1)


@app.command()
def benchmark(cases: Path = typer.Option(Path("benchmark/cases.json")),
              out: Optional[Path] = typer.Option(None, help="Write the Markdown results here")):
    """Run the simulated benchmark and print the results."""
    from . import benchmark as bm
    md = bm.render(bm.run(cases))
    if out:
        out.write_text(md.rstrip("\n") + "\n", encoding="utf-8")
    typer.echo(md)


@audit_app.command("verify")
def audit_verify(db: Path):
    """Verify the hash chain of an audit database."""
    ok, bad = AuditLog(db).verify()
    typer.echo("OK" if ok else f"TAMPERED at seq {bad}")
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
