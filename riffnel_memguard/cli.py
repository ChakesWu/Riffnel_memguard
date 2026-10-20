"""Command line entry point."""
from __future__ import annotations

import tempfile
from pathlib import Path

import typer

from . import demo as demo_mod
from .core.audit import AuditLog

app = typer.Typer(help="Riffnel_memguard: memory error investigation and correction verification.")
audit_app = typer.Typer(help="Audit log commands.")
app.add_typer(audit_app, name="audit")


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


@audit_app.command("verify")
def audit_verify(db: Path):
    """Verify the hash chain of an audit database."""
    ok, bad = AuditLog(db).verify()
    typer.echo("OK" if ok else f"TAMPERED at seq {bad}")
    raise typer.Exit(0 if ok else 1)


if __name__ == "__main__":
    app()
