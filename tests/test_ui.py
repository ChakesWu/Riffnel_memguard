import json
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
