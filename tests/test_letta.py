"""Integration tests against a REAL Letta server (skipped when none is reachable).

Setup used in development (see docs/INTEGRATION.md): Letta 0.16.7 from PyPI with dependencies resolved as of its release
date, a local PostgreSQL + pgvector, and a local OpenAI-compatible embeddings stand-in (started below).
Set RIFFNEL_LETTA_URL to point at the server (default http://localhost:8283).
"""
import os
import shutil
import subprocess

import pytest

pytest.importorskip("letta_client")
from letta_client import Letta  # noqa: E402

from riffnel_memguard.adapters.base import MemoryListingTruncated  # noqa: E402
from riffnel_memguard.adapters.letta_adapter import LettaAdapter  # noqa: E402
from riffnel_memguard.core.models import MemoryRecord  # noqa: E402
from riffnel_memguard.adapters.letta_testkit import (  # noqa: E402
    create_test_agent, delete_agent_and_archives, start_hash_embedding_server)

URL = os.environ.get("RIFFNEL_LETTA_URL", "http://localhost:8283")


@pytest.fixture(scope="module")
def letta():
    client = Letta(base_url=URL, timeout=30)
    try:
        client.health()
    except Exception:
        pytest.skip(f"no Letta server at {URL}")
    srv, url = start_hash_embedding_server()
    yield client, url
    srv.shutdown()


@pytest.fixture
def store(letta):
    client, embed_url = letta
    ag = create_test_agent(client, embed_url, "riffnel-test")
    yield LettaAdapter(client, ag.id)
    delete_agent_and_archives(client, ag.id)


def rec(id, content, **kw):
    return MemoryRecord(id=id, content=content, **kw)


def test_roundtrip_status_scope_and_logical_ids(store):
    store.add(rec("m1", "金卡免年费需要每年刷满3笔。", scope={"product": "gold_card"}, key="k", value=3,
                  derived_from=["z"], written_at="2025-02-01", kind="fact"))
    got = store.get("m1")
    assert (got.scope, got.key, got.value, got.derived_from, got.status, got.written_at) == (
        {"product": "gold_card"}, "k", 3, ["z"], "active", "2025-02-01")
    assert [r.id for r, _ in store.search("金卡免年费要刷几笔", {"product": "gold_card"}, 3)] == ["m1"]
    assert store.search("金卡免年费要刷几笔", {"product": "silver_card"}, 3) == []
    old_passage = store._grouped()["m1"][0].id
    store.invalidate("m1", "x")
    assert store.get("m1").status == "invalidated" and store.search("金卡免年费", {"product": "gold_card"}, 3) == []
    assert store._grouped()["m1"][0].id != old_passage  # Letta cannot modify a passage: it was replaced
    store.restore("m1")
    store.rescope("m1", {"product": "silver_card"})
    got = store.get("m1")
    assert (got.status, got.scope, got.key, got.value, got.derived_from) == ("active", {"product": "silver_card"}, "k", 3, ["z"])
    assert len(store.list()) == 1  # replacement left no duplicate behind


def test_passages_written_by_the_agent_itself_are_visible_and_keep_their_id(store, letta):
    client, _ = letta
    (p,) = client.agents.passages.create(store.agent_id, text="客户反馈：银卡年费为500元。")  # no riffnel tags
    assert [(r.id, r.status, r.scope) for r in store.list()] == [(p.id, "active", {})]
    store.quarantine(p.id, "x")
    assert store.get(p.id).status == "quarantined" and store.get(p.id).content == "客户反馈：银卡年费为500元。"


def test_delete_removes_the_passage(store):
    store.add(rec("a", "客户手机号13800000000。", scope={"user": "u"}))
    store.add(rec("b", "金卡年费为1000元。"))
    store.delete("a")
    assert store.get("a") is None and [r.id for r in store.list()] == ["b"]
    store.delete("a")  # deleting twice is harmless


def test_cursor_pagination_and_loud_truncation(store, letta):
    client, _ = letta
    for i in range(5):
        store.add(rec(f"p{i}", f"事实{i}号"))
    small = LettaAdapter(client, store.agent_id, page_size=2)
    assert sorted(r.id for r in small.list()) == [f"p{i}" for i in range(5)]  # three pages of 2, 2, 1
    with pytest.raises(MemoryListingTruncated):
        LettaAdapter(client, store.agent_id, page_size=2, max_items=4).list()


def test_untested_server_version_warns(letta, monkeypatch):
    client, _ = letta
    import importlib.metadata as md
    real = md.version
    monkeypatch.setattr(md, "version", lambda n: "9.9.9" if n == "letta-client" else real(n))
    with pytest.warns(RuntimeWarning, match="not tested"):
        LettaAdapter(client, "agent-x")


def test_canary_deleting_an_agent_leaves_its_archive_and_passages(letta):
    """Documents observed Letta 0.16.7 behaviour: if an upstream release changes it, this test fails and the README
    note about erasing whole agents must be revisited."""
    client, embed_url = letta
    ag = create_test_agent(client, embed_url, "riffnel-canary")
    LettaAdapter(client, ag.id).add(rec("x", "客户手机号13800000000。"))
    client.agents.delete(ag.id)  # the naive way
    try:
        orphans = [a for a in client.archives.list(limit=100) if a.name.startswith("riffnel-canary")]
        assert orphans, "the archive vanished with the agent: Letta behaviour changed"
        uri = os.environ.get("RIFFNEL_LETTA_PG_URI", "postgresql://letta:letta@127.0.0.1:5432/letta")
        if shutil.which("pg_dump"):  # the API cannot read an orphan archive's passages, the database still holds them
            dump = subprocess.run(["pg_dump", "--data-only", uri], capture_output=True, text=True, encoding="utf-8").stdout
            assert "13800000000" in dump
    finally:
        for a in list(client.archives.list(limit=100)):  # materialise first: deleting while paging breaks the cursor
            if a.name.startswith("riffnel-canary"):
                client.archives.delete(a.id)
    assert not [a for a in client.archives.list(limit=100) if a.name.startswith("riffnel-canary")]
