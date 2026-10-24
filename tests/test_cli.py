import re

from typer.testing import CliRunner

from riffnel_memguard.cli import app

run = CliRunner().invoke


def ok(r):
    assert r.exit_code == 0, r.output
    return r.output


def test_stepwise_stale_flow_and_report(tmp_path):
    ws = ["--ws", str(tmp_path)]
    ok(run(app, ["init", *ws]))
    ok(run(app, ["ask", "金卡免年费需要刷几笔？", "--scope", "product=gold_card", "--at", "2026-08-10", *ws]))
    ok(run(app, ["investigate", "inc_001", *ws]))
    pid = re.search(r"plan_\w+", ok(run(app, ["plan", "inc_001", "--as-of", "2026-09-01", *ws]))).group(0)
    assert run(app, ["apply", pid, *ws]).exit_code != 0  # not approved yet
    ok(run(app, ["diff", pid, *ws]))
    ok(run(app, ["approve", pid, "--by", "tester", *ws]))
    ok(run(app, ["apply", pid, *ws]))
    ok(run(app, ["verify", pid, *ws]))
    md = (tmp_path / "reports" / f"{pid}.md").read_text(encoding="utf-8") if ok(run(app, ["report", pid, *ws])) else ""
    assert "M1" in md and "重放：通过" in md and "快照 SHA-256" in md
    ok(run(app, ["audit", "verify", str(tmp_path / "audit.db")]))


def test_stepwise_erasure_flow_masks_report(tmp_path):
    ws = ["--ws", str(tmp_path)]
    ok(run(app, ["init", *ws]))
    ok(run(app, ["simulate-delete", "m_phone_raw", *ws]))
    out = ok(run(app, ["erase", "--subject", "user=u_demo", "--target", "13800000000",
                       "--description", "客户张三的手机号 13800000000", *ws]))
    pid = re.search(r"plan_\w+", out).group(0)
    assert "13800000000" not in ok(run(app, ["diff", pid, *ws]))
    ok(run(app, ["approve", pid, "--by", "tester", *ws]))
    ok(run(app, ["apply", pid, *ws]))
    ok(run(app, ["verify", pid, *ws]))
    ok(run(app, ["report", pid, *ws]))
    md = (tmp_path / "reports" / f"{pid}.md").read_text(encoding="utf-8")
    assert "13800000000" not in md and "138****0000" in md and "硬性关卡均无命中" in md


def test_revalidate_command(tmp_path):
    ws = ["--ws", str(tmp_path)]
    ok(run(app, ["init", *ws]))
    assert "过期" in ok(run(app, ["revalidate", "--as-of", "2026-09-01", *ws]))


def test_no_attribution_message(tmp_path):
    ws = ["--ws", str(tmp_path)]
    ok(run(app, ["init", *ws]))
    ok(run(app, ["ask", "金卡年费是多少？", "--scope", "product=gold_card", "--at", "2026-08-10", *ws]))
    assert "无法归因" in ok(run(app, ["investigate", "inc_001", *ws]))


def test_every_documented_command_exists():
    """Guards against a refactor silently removing a command the README promises."""
    from typer.main import get_command
    documented = {"init", "ask", "investigate", "plan", "diff", "approve", "apply", "rollback", "verify", "report",
                  "revalidate", "erase", "erase-discard", "simulate-delete", "export-memwall", "import-memwall", "link",
                  "impact", "scan", "benchmark", "demo", "ui", "audit"}
    assert documented <= set(get_command(app).commands)
