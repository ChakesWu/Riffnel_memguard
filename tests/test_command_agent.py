import json
import re
import shlex
import sys

import pytest
from typer.testing import CliRunner

from riffnel_memguard.agent.command import AgentCommandError, CommandAgent
from riffnel_memguard.cli import app

PY = sys.executable


def script(tmp_path, body, name="agent.py"):
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return [PY, str(p)]


def test_protocol_roundtrip_ignores_log_lines_and_passes_scope(tmp_path):
    argv = script(tmp_path, "import sys, json\nreq = json.loads(sys.stdin.readline())\nprint('starting...')\n"
                            "print(json.dumps({'answer': req['question'] + '|' + req['scope']['product'], 'retrieved_ids': ['a', 'b']}, ensure_ascii=False))\n")
    assert CommandAgent(argv).answer("金卡？", {"product": "gold"}) == ("金卡？|gold", ["a", "b"])


def test_command_string_is_split_without_a_shell(tmp_path):
    argv = script(tmp_path, "import json,sys\nsys.stdin.readline()\nprint(json.dumps({'answer': 'ok'}))\n")
    agent = CommandAgent(shlex.join(argv))
    assert agent.answer("q", {}) == ("ok", []) and agent.model_name.startswith("command:")
    # shell metacharacters are plain arguments, not interpreted
    marker = tmp_path / "pwned"
    agent2 = CommandAgent(shlex.join(argv) + f" ; touch {marker}")
    agent2.answer("q", {})
    assert not marker.exists()


@pytest.mark.parametrize("body,needle", [
    ("import sys\nsys.exit(3)", "exited with 3"),
    ("import sys\nsys.stderr.write('boom')\nsys.exit(1)", "boom"),
    ("print('not json')", "not JSON"),
    ("pass", "printed nothing"),
    ("print('{\"answer\": 5}')", 'string field "answer"'),
    ("print('[1]')", 'string field "answer"'),
    ("print('{\"answer\": \"x\", \"retrieved_ids\": [1]}')", "retrieved_ids"),
    ("print('{\"answer\": \"x\", \"retrieved_ids\": \"a\"}')", "retrieved_ids"),
])
def test_protocol_violations_raise_clear_errors(tmp_path, body, needle):
    with pytest.raises(AgentCommandError, match=re.escape(needle)):
        CommandAgent(script(tmp_path, body)).answer("q", {})


def test_missing_command_and_timeout(tmp_path):
    with pytest.raises(AgentCommandError, match="not found"):
        CommandAgent(["definitely-not-a-real-command-xyz"]).answer("q", {})
    with pytest.raises(AgentCommandError, match="timed out"):
        CommandAgent(script(tmp_path, "import time\ntime.sleep(5)"), timeout=0.5).answer("q", {})
    with pytest.raises(AgentCommandError, match="empty"):
        CommandAgent("")


def test_end_to_end_with_an_external_agent_command(tmp_path):
    run = CliRunner().invoke
    ws, log = tmp_path / "ws", tmp_path / "calls.log"
    base = ["--ws", str(ws)]
    cmd = shlex.join([PY, "-m", "riffnel_memguard.agent.stdio_agent", "--workspace", str(ws), "--log", str(log)])
    assert run(app, ["init", *base]).exit_code == 0
    r = run(app, ["ask", "金卡免年费需要刷几笔？", "--scope", "product=gold_card", "--at", "2026-08-10",
                  "--agent-cmd", cmd, *base])
    assert r.exit_code == 0 and "3笔" in r.output
    assert json.loads((ws / "state.json").read_text(encoding="utf-8"))["incidents"]["inc_001"]["agent_cmd"] == cmd
    assert run(app, ["investigate", "inc_001", *base]).exit_code == 0
    pid = re.search(r"plan_\w+", run(app, ["plan", "inc_001", "--as-of", "2026-09-01", *base]).output).group(0)
    assert run(app, ["approve", pid, "--by", "tester", *base]).exit_code == 0
    assert run(app, ["apply", pid, *base]).exit_code == 0
    calls_before = len(log.read_text(encoding="utf-8").splitlines())
    r = run(app, ["verify", pid, *base])  # no --agent-cmd: reuses the one stored with the incident
    assert r.exit_code == 0, r.output
    # 1 replay + 3 regression questions went through the external command
    assert len(log.read_text(encoding="utf-8").splitlines()) - calls_before == 4


def test_cli_reports_agent_errors_without_a_traceback(tmp_path):
    run = CliRunner().invoke
    base = ["--ws", str(tmp_path / "ws")]
    run(app, ["init", *base])
    r = run(app, ["ask", "q", "--scope", "product=x", "--at", "2026-08-10", "--agent-cmd", "no-such-agent-binary", *base])
    assert r.exit_code != 0 and "not found" in r.output and "Traceback" not in r.output


@pytest.mark.skipif(__import__("shutil").which("node") is None, reason="node is not installed")
def test_a_node_agent_works_through_the_same_protocol(tmp_path):
    from pathlib import Path
    run = CliRunner().invoke
    ws = tmp_path / "ws"
    base = ["--ws", str(ws)]
    js = Path(__file__).resolve().parents[1] / "examples" / "agent_cmd" / "agent.js"
    cmd = shlex.join(["node", str(js), str(ws / "memories.json")])
    run(app, ["init", *base])
    assert run(app, ["ask", "金卡免年费需要刷几笔？", "--scope", "product=gold_card", "--at", "2026-08-10",
                     "--agent-cmd", cmd, *base]).exit_code == 0
    run(app, ["investigate", "inc_001", *base])
    pid = re.search(r"plan_\w+", run(app, ["plan", "inc_001", "--as-of", "2026-09-01", *base]).output).group(0)
    run(app, ["approve", pid, "--by", "t", *base])
    run(app, ["apply", pid, *base])
    assert run(app, ["verify", pid, *base]).exit_code == 0
