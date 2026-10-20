import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

APP = str(Path(__file__).resolve().parents[1] / "riffnel_memguard" / "ui" / "app.py")


def click(at, label):
    next(b for b in at.button if b.label == label).click().run()


def test_ui_stale_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("RIFFNEL_WS", str(tmp_path))
    at = AppTest.from_file(APP, default_timeout=60).run()
    click(at, "用仿真示例初始化")
    at.sidebar.radio[0].set_value("事故调查").run()
    click(at, "提问并记录事故")
    click(at, "调查")
    click(at, "生成修正方案")
    at.text_input(key=next(t.key for t in at.text_input if t.key and t.key.startswith("by_"))).set_value("tester").run()
    click(at, "审批")
    click(at, "应用")
    click(at, "验证")
    assert not at.exception
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    (plan,) = state["plans"].values()
    assert plan["status"] == "applied" and plan["approved_by"] == "tester"
    assert all(v["passed"] for v in state["verifications"][plan["id"]].values())


def test_ui_runs_an_external_agent_when_enabled(tmp_path, monkeypatch):
    import shlex
    import sys
    monkeypatch.setenv("RIFFNEL_WS", str(tmp_path))
    monkeypatch.setenv("RIFFNEL_UI_ALLOW_AGENT_CMD", "1")
    at = AppTest.from_file(APP, default_timeout=60).run()
    click(at, "用仿真示例初始化")
    at.sidebar.radio[0].set_value("事故调查").run()
    log = tmp_path / "calls.log"
    cmd = shlex.join([sys.executable, "-m", "riffnel_memguard.agent.stdio_agent", "--workspace", str(tmp_path),
                      "--log", str(log)])
    at.sidebar.text_input(key="agent_cmd").set_value(cmd).run()
    click(at, "提问并记录事故")
    click(at, "调查")
    click(at, "生成修正方案")
    at.text_input(key=next(t.key for t in at.text_input if t.key and t.key.startswith("by_"))).set_value("tester").run()
    click(at, "审批")
    click(at, "应用")
    before = len(log.read_text(encoding="utf-8").splitlines())
    click(at, "验证")
    assert not at.exception
    state = json.loads((tmp_path / "state.json").read_text(encoding="utf-8"))
    (plan,) = state["plans"].values()
    assert state["incidents"]["inc_001"]["agent_cmd"] == cmd
    assert all(v["passed"] for v in state["verifications"][plan["id"]].values())
    assert len(log.read_text(encoding="utf-8").splitlines()) - before == 4  # replay + 3 regression via the command


def test_ui_does_not_execute_external_commands_by_default(tmp_path, monkeypatch):
    from riffnel_memguard import service
    from riffnel_memguard.core.workspace import Workspace
    monkeypatch.setenv("RIFFNEL_WS", str(tmp_path))
    monkeypatch.delenv("RIFFNEL_UI_ALLOW_AGENT_CMD", raising=False)
    marker = tmp_path / "executed"
    w = Workspace(tmp_path)
    w.init(True)
    # an incident recorded from the CLI with an external command that would leave a marker if it ever ran
    cmd = f"{sys.executable} -c \"open(r'{marker}','w').write('x')\""
    st_ = w.state()
    st_["incidents"]["inc_001"] = {"id": "inc_001", "occurred_at": "2026-08-10", "agent_id": "agent-cmd", "scope": {"product": "gold_card"},
                                   "question": "金卡免年费需要刷几笔？", "answer": "金卡免年费需要每年刷满3笔。",
                                   "retrieved_ids": ["m_gold_waiver"], "agent_cmd": cmd, "agent_timeout": 60.0}
    w.save_state(st_)
    service.investigate(w, "inc_001")
    service.plan_incident(w, "inc_001", "2026-09-01")
    (pid,) = w.state()["plans"]
    service.approve(w, pid, "t")
    service.apply(w, pid)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.sidebar.radio[0].set_value("事故调查").run()
    assert not any(t.key == "agent_cmd" for t in at.sidebar.text_input)  # no command box when disabled
    st_ = w.state()
    at.session_state["plan"] = pid
    at.run()
    click(at, "验证")
    assert any("默认不执行" in wmsg.value for wmsg in at.warning)
    assert not marker.exists() and pid not in w.state()["verifications"]
