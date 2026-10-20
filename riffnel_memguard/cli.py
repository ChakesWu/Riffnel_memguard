"""Command line entry point."""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Optional

import typer

from . import demo as demo_mod
from . import service
from .core.audit import AuditLog
from .core.workspace import Workspace
from .report.markdown import mask_text

app = typer.Typer(help="Riffnel_memguard: memory error investigation and correction verification.")
audit_app = typer.Typer(help="Audit log commands.")
app.add_typer(audit_app, name="audit")

WS_OPT = typer.Option(Path(os.environ.get("RIFFNEL_WS", ".riffnel")), "--ws", help="Workspace directory")


def _scope(items: list[str]) -> dict:
    return service._parse_scope(items)


def _call(fn, *a, **k):
    try:
        return fn(*a, **k)
    except (KeyError, ValueError, PermissionError) as e:
        raise typer.BadParameter(str(e).strip("'"))


@app.command()
def init(ws: Path = WS_OPT, example: bool = typer.Option(True, help="Copy the simulated bank example")):
    """Create a workspace (with the simulated bank example by default)."""
    Workspace(ws).init(example)
    typer.echo(f"已初始化 {ws}")


@app.command()
def ask(question: str, scope: list[str] = typer.Option(..., "--scope", help="key=value, repeatable"),
        at: str = typer.Option(..., help="Incident date, YYYY-MM-DD"), ws: Path = WS_OPT):
    """Ask the reference agent and record the exchange as an incident."""
    w = Workspace(ws)
    iid = service.ask(w, question, _scope(scope), at)
    typer.echo(f"{iid}\n答：{w.state()['incidents'][iid]['answer']}")


@app.command()
def investigate(incident_id: str, ws: Path = WS_OPT):
    """Find the memories responsible for a wrong answer."""
    findings = _call(service.investigate, Workspace(ws), incident_id)
    if not findings:
        typer.echo("无法归因：错误不来自被取用的记忆（请检查提示词或模型层）。")
    for f in findings:
        typer.echo(f"{f.cls} {f.memory_id} 置信度 {f.confidence}：{mask_text(f.evidence.get('memory_text', ''))}")


@app.command()
def plan(incident_id: str, as_of: str = typer.Option(..., help="Date the correction should be valid at"),
         ws: Path = WS_OPT):
    """Draft a correction plan from an incident's findings."""
    typer.echo(_call(service.plan_incident, Workspace(ws), incident_id, as_of))


@app.command()
def revalidate(as_of: str = typer.Option(...), ws: Path = WS_OPT):
    """After a source update: find active memories that still hold a superseded value."""
    fs, pid = service.revalidate(Workspace(ws), as_of)
    typer.echo(f"{len(fs)} 条记忆过期，方案 {pid}" if fs else "没有依赖旧版本的有效记忆。")


@app.command()
def erase(subject: list[str] = typer.Option(..., "--subject", help="key=value scope of the data subject"),
          target: list[str] = typer.Option(..., "--target", help="Exact value that must be gone, repeatable"),
          description: str = typer.Option("", help="Text used for the semantic probe"),
          ws: Path = WS_OPT):
    """Register an erasure request, look for residue, and draft a plan."""
    fs, pid = service.erase(Workspace(ws), _scope(subject), target, description)
    typer.echo(f"发现 {len(fs)} 处残留，方案 {pid}" if fs else "未发现残留。")


@app.command("export-memwall")
def export_memwall(out: Path, ws: Path = WS_OPT):
    """Write the workspace memories in a shape `memwall scan` reads."""
    n = service.export_memwall(Workspace(ws), out)
    typer.echo(f"已导出 {n} 条到 {out}；下一步：memwall scan {out} --json report.json")


@app.command("import-memwall")
def import_memwall(report: Path, min_severity: str = typer.Option("medium", help="info|low|medium|high|critical"),
                   ws: Path = WS_OPT):
    """Import a `memwall scan --json PATH` report as M6 findings and draft a quarantine plan."""
    fs, unmatched, pid = _call(service.import_memwall, Workspace(ws), report, min_severity)
    for f in fs:
        typer.echo(f"M6 {f.memory_id}（memwall {f.evidence['severity']}）：{', '.join(f.evidence['rules'])}")
    if unmatched:
        typer.echo(f"未能匹配到本工作区记忆：{', '.join(unmatched)}")
    typer.echo(f"方案 {pid}" if pid else "没有需要处理的发现。")


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
    for line in _call(service.diff, Workspace(ws), plan_id):
        typer.echo(mask_text(line))


@app.command()
def approve(plan_id: str, by: str = typer.Option(...), ws: Path = WS_OPT):
    _call(service.approve, Workspace(ws), plan_id, by)
    typer.echo(f"{plan_id} 已由 {by} 审批")


@app.command()
def apply(plan_id: str, ws: Path = WS_OPT):
    _call(service.apply, Workspace(ws), plan_id)
    typer.echo(f"{plan_id} 已应用")


@app.command()
def rollback(plan_id: str, by: str = typer.Option(...), ws: Path = WS_OPT):
    skipped = _call(service.rollback, Workspace(ws), plan_id, by)
    typer.echo(f"已回滚；无法回滚的删除：{skipped}" if skipped else "已回滚")


@app.command()
def verify(plan_id: str, question: list[str] = typer.Option(["我的手机号是多少？"], "--question"), ws: Path = WS_OPT):
    """Run replay + regression (incident plans) or the four-layer probe (erasure plans)."""
    res = _call(service.verify, Workspace(ws), plan_id, question)
    for k, v in res.items():
        typer.echo(f"{k}: {'通过' if v['passed'] else '失败'}")
    raise typer.Exit(0 if all(v["passed"] for v in res.values()) else 1)


@app.command()
def report(plan_id: str, ws: Path = WS_OPT):
    """Write the Markdown evidence report."""
    typer.echo(str(_call(service.report, Workspace(ws), plan_id)))


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
def ui(ws: Path = WS_OPT, port: int = typer.Option(8501), address: str = typer.Option("localhost")):
    """Launch the Streamlit web UI (needs the `ui` extra)."""
    import subprocess
    import sys
    app_path = Path(__file__).parent / "ui" / "app.py"
    raise typer.Exit(subprocess.call([sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port",
                                      str(port), "--server.address", address, "--server.headless", "true",
                                      "--", "--ws", str(ws)]))


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
