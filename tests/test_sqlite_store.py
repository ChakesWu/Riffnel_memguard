import sqlite3

import pytest

from riffnel_memguard import demo
from riffnel_memguard.adapters.sqlite_store import SQLiteStore
from riffnel_memguard.core.models import MemoryRecord
from riffnel_memguard.probes.erasure import bytes_residue


def rec(id, content, **kw):
    return MemoryRecord(id=id, content=content, **kw)


def test_roundtrip_status_scope_search(tmp_path):
    s = SQLiteStore(tmp_path / "m.db")
    s.add(rec("a", "金卡免年费需要每年刷满3笔。", scope={"product": "gold_card"}, key="k", value=3,
              derived_from=["z"], written_at="2025-02-01"))
    got = s.get("a")
    assert (got.scope, got.key, got.value, got.derived_from, got.status) == ({"product": "gold_card"}, "k", 3, ["z"], "active")
    assert [r.id for r, _ in s.search("金卡免年费", {"product": "gold_card"}, 3)] == ["a"]
    assert s.search("金卡免年费", {"product": "silver_card"}, 3) == []
    s.invalidate("a", "x")
    assert s.get("a").status == "invalidated" and s.search("金卡免年费", {"product": "gold_card"}, 3) == []
    s.restore("a")
    s.rescope("a", {"product": "silver_card"})
    assert s.get("a").scope == {"product": "silver_card"} and s.get("a").key == "k"
    with pytest.raises(KeyError):
        s.invalidate("nope", "x")


def test_works_on_a_foreign_table_with_custom_columns(tmp_path):
    db = tmp_path / "app.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE notes (note_id INTEGER PRIMARY KEY, body TEXT, owner TEXT, state TEXT)")
        c.execute("INSERT INTO notes VALUES (1, '金卡年费为1000元。', 'u1', 'active')")
    s = SQLiteStore(db, table="notes", id_col="note_id", content_col="body", scope_cols=("owner",), status_col="state",
                    kind_col=None, key_col=None, value_col=None, derived_col=None, written_col=None, create=False)
    assert [(r.id, r.scope, r.status) for r in s.list()] == [("1", {"owner": "u1"}, "active")]
    s.quarantine("1", "x")
    assert s.get("1").status == "quarantined"
    with pytest.raises(ValueError):
        SQLiteStore(db, table="missing", create=False)
    with pytest.raises(ValueError):
        SQLiteStore(db, table="notes; DROP TABLE notes")  # identifiers are validated


def test_no_status_column_cannot_invalidate(tmp_path):
    db = tmp_path / "app.db"
    with sqlite3.connect(db) as c:
        c.execute("CREATE TABLE notes (id TEXT, body TEXT)")
        c.execute("INSERT INTO notes VALUES ('1', 'x')")
    s = SQLiteStore(db, table="notes", content_col="body", scope_cols=(), status_col=None, kind_col=None,
                    key_col=None, value_col=None, derived_col=None, written_col=None, create=False)
    with pytest.raises(NotImplementedError):
        s.invalidate("1", "x")


def test_delete_leaves_no_bytes(tmp_path):
    s = SQLiteStore(tmp_path / "m.db")
    for i in range(20):
        s.add(rec(f"r{i}", f"客户手机号13800000000-{'x' * 200}", scope={"user": "u"}))
    for i in range(20):
        s.delete(f"r{i}")
    assert s.list() == [] and bytes_residue(tmp_path, ["13800000000"]) == []


def test_demos_run_on_sqlite(tmp_path):
    assert demo.run_stale(tmp_path / "a", log=lambda *_: None, store_kind="sqlite")["passed"]
    r = demo.run_erasure(tmp_path / "b", log=lambda *_: None, store_kind="sqlite")
    assert r["passed"] and bytes_residue(tmp_path / "b", ["13800000000", "138 0000 0000"]) == [
        "memories.json"]  # the seed JSON copy is outside the SQLite store; the .db file itself is clean
