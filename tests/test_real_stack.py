"""Tests on the real stack: Mem0 + local Qdrant + Pydantic AI. Skipped when the extras are not installed."""
import pytest

pytest.importorskip("mem0")
pytest.importorskip("pydantic_ai")

from riffnel_memguard import demo_real  # noqa: E402
from riffnel_memguard.adapters.mem0_adapter import Mem0Adapter, make_offline_memory  # noqa: E402
from riffnel_memguard.agent.enterprise import EnterpriseBankAgent  # noqa: E402
from riffnel_memguard.core.models import MemoryRecord  # noqa: E402


@pytest.fixture
def store(tmp_path):
    return Mem0Adapter(make_offline_memory(tmp_path / "mem0"), agent_id="t")


def rec(id, content, **kw):
    return MemoryRecord(id=id, content=content, **kw)


def test_adapter_roundtrip_status_and_scope(store):
    store.add(rec("m1", "金卡免年费需要每年刷满3笔。", scope={"product": "gold_card"}, key="k", value=3, written_at="2025-02-01"))
    got = store.get("m1")
    assert (got.scope, got.key, got.value, got.status) == ({"product": "gold_card"}, "k", 3, "active")
    assert [r.id for r, _ in store.search("金卡免年费要刷几笔", {"product": "gold_card"}, 3)] == ["m1"]
    assert store.search("金卡免年费要刷几笔", {"product": "silver_card"}, 3) == []  # scope filter
    store.invalidate("m1", "x")
    assert store.get("m1").status == "invalidated" and store.search("金卡免年费", {"product": "gold_card"}, 3) == []
    store.restore("m1")
    assert store.get("m1").status == "active"
    store.rescope("m1", {"product": "silver_card"})
    assert store.get("m1").scope == {"product": "silver_card"} and store.get("m1").key == "k"


def test_mem0_delete_leaves_history_which_adapter_exposes_and_scrubs(store):
    store.add(rec("p", "客户手机号13800000000。", scope={"user": "u"}))
    uuid = store._resolve("p")["id"]
    store.m.delete(uuid)  # Mem0's own delete
    assert store.get("p") is None
    assert any("13800000000" in t.content for t in store.traces())  # canary: Mem0 keeps the text in history.db
    store.add(rec("q", "客户手机号13800000000。", scope={"user": "u"}))
    store.delete("q")  # the adapter's delete scrubs history for this memory
    leftovers = [t for t in store.traces() if "13800000000" in t.content]
    assert len(leftovers) == 2  # only p's rows remain; q's were purged
    store.delete(leftovers[0].id)
    assert len([t for t in store.traces() if "13800000000" in t.content]) == 1


def test_enterprise_agent_answers_from_recall_and_declines_without_memory(store):
    agent = EnterpriseBankAgent(store)
    assert agent.answer("金卡免年费需要刷几笔？", {"product": "gold_card"}) == ("抱歉，我没有相关信息。", [])
    store.add(rec("m1", "金卡免年费需要每年刷满3笔。", scope={"product": "gold_card"}))
    answer, retrieved = agent.answer("金卡免年费需要刷几笔？", {"product": "gold_card"})
    assert answer == "金卡免年费需要每年刷满3笔。" and retrieved == ["m1"]


def test_real_stack_stale_scenario(tmp_path):
    r = demo_real.run_stale(tmp_path, log=lambda *_: None)
    assert r["passed"]
    adds = [a for a in r["plan"].actions if a.type == "add"]
    assert len(adds) == 1  # one replacement fact even though the stale summary was retrieved too


def test_real_stack_erasure_scenario_and_independent_byte_scan(tmp_path):
    r = demo_real.run_erasure(tmp_path, log=lambda *_: None)
    assert r["passed"]
    assert r["bytes_before"] and not r["bytes_after"]  # files held the number before; none after
    assert not r["pre"]["clean"] and r["post"]["clean"]
