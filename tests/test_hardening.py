"""Regression tests for the defects found when checking the tool against its own claims."""
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from typer.testing import CliRunner

from riffnel_memguard import service
from riffnel_memguard.adapters.base import JsonFileStore
from riffnel_memguard.cli import app
from riffnel_memguard.core import locking
from riffnel_memguard.core.audit import AuditLog
from riffnel_memguard.core.workspace import Workspace
from riffnel_memguard.probes.erasure import bytes_residue
from riffnel_memguard.report.markdown import mask_text

run = CliRunner().invoke
NEEDLES = ["13800000000", "138 0000 0000", "138-0000-0000"]


def ws(tmp_path):
    w = Workspace(tmp_path / "ws")
    w.init(True)
    return w


def stale_plan(w):
    fs, pid = service.scan(w, "2026-09-01")
    assert pid
    return pid


# --- 1. erasing data must not leave it in the tool's own files -----------------------------------------------
def test_erasure_leaves_no_copy_in_the_workspace(tmp_path):
    base = ["--ws", str(tmp_path / "ws")]
    assert run(app, ["init", *base]).exit_code == 0
    # an incident whose question and answer contain the personal data, and an old unmasked report mentioning it
    assert "13800000000" in run(app, ["ask", "我的手机号是多少？", "--scope", "user=u_demo", "--at", "2026-08-10", *base]).output
    reports = tmp_path / "ws" / "reports"
    reports.mkdir()
    (reports / "old.md").write_text("客户手机号 138 0000 0000", encoding="utf-8")
    (reports / "unrelated.md").write_text("无关内容", encoding="utf-8")
    run(app, ["simulate-delete", "m_phone_raw", *base])
    out = run(app, ["erase", "--subject", "user=u_demo", "--target", "13800000000",
                    "--description", "客户张三的手机号 13800000000", *base]).output
    pid = re.search(r"plan_\w+", out).group(0)
    state_text = (tmp_path / "ws" / "state.json").read_text(encoding="utf-8")
    assert "targets_masked" in state_text and '"targets"' not in state_text and '"description"' not in state_text
    secret = tmp_path / "ws" / "secrets" / "er_001.json"
    assert secret.exists() and (secret.stat().st_mode & 0o077 == 0 or os.name == "nt")  # owner-only
    run(app, ["approve", pid, "--by", "t", *base])
    applied = run(app, ["apply", pid, *base]).output
    assert "已清除工作区状态" in applied and "secrets/" in applied
    assert not (reports / "old.md").exists() and (reports / "unrelated.md").exists()
    st = json.loads((tmp_path / "ws" / "state.json").read_text(encoding="utf-8"))
    assert "已遮蔽" in st["incidents"]["inc_001"]["answer"] and st["plans"][pid]["scrub"]["strings"] >= 1
    assert run(app, ["verify", pid, *base]).exit_code == 0
    assert not secret.exists()  # dropped once the verification passed
    assert bytes_residue(tmp_path / "ws", NEEDLES) == []  # nothing left anywhere in the workspace
    events = " ".join(e[3] for e in AuditLog(tmp_path / "ws" / "audit.db").events())
    assert "scrub" in events and "targets_discarded" in events


def test_verify_after_discard_explains_instead_of_crashing(tmp_path):
    w = ws(tmp_path)
    w.store.delete("m_phone_raw")
    fs, pid = service.erase(w, {"user": "u_demo"}, ["13800000000"], "x")
    eid = w.state()["plans"][pid]["erasure_id"]
    assert service.erase_discard(w, eid) is True and service.erase_discard(w, eid) is False
    with pytest.raises(ValueError, match="no longer stored"):
        service.verify(w, pid, ["我的手机号是多少？"])


def test_workspace_from_before_secrets_is_migrated_on_verify(tmp_path):
    w = ws(tmp_path)
    w.store.delete("m_phone_raw")
    fs, pid = service.erase(w, {"user": "u_demo"}, ["13800000000"], "x")
    eid = w.state()["plans"][pid]["erasure_id"]
    with w.transaction() as st:  # simulate an old state file that kept the targets
        st["erasures"][eid]["targets"] = ["13800000000"]
        st["erasures"][eid]["description"] = "x"
    w.drop_secret(eid)
    service.approve(w, pid, "t")
    service.apply(w, pid)
    service.verify(w, pid, ["我的手机号是多少？"])
    assert "targets" not in w.state()["erasures"][eid]


def test_mask_text_covers_email_addresses():
    assert mask_text("联系 zhang.san@example.com 或 13800000000") == "联系 z***@example.com 或 138****0000"


# --- 2. plan state machine and approver policy ---------------------------------------------------------------
def test_plan_state_machine_is_enforced(tmp_path):
    w = ws(tmp_path)
    pid = stale_plan(w)
    with pytest.raises(PermissionError):
        service.rollback(w, pid, "t")  # nothing applied yet
    service.approve(w, pid, "alice")
    with pytest.raises(PermissionError, match="draft or rolled-back"):
        service.approve(w, pid, "bob")  # already approved: the approver cannot be swapped
    service.apply(w, pid)
    with pytest.raises(PermissionError):
        service.apply(w, pid)  # applying twice
    with pytest.raises(PermissionError, match="draft or rolled-back"):
        service.approve(w, pid, "anyone")  # an applied plan cannot be approved again
    assert w.state()["plans"][pid]["status"] == "applied"
    service.rollback(w, pid, "alice")
    service.approve(w, pid, "alice")  # after a rollback it can be approved and applied again
    service.apply(w, pid)
    assert w.state()["plans"][pid]["status"] == "applied"


def test_approver_policy(tmp_path, monkeypatch):
    w = ws(tmp_path)
    monkeypatch.setenv("RIFFNEL_USER", "drafter")
    pid = stale_plan(w)
    assert w.state()["plans"][pid]["created_by"] == "drafter"
    with pytest.raises(PermissionError, match="name is required"):
        service.approve(w, pid, "  ")
    monkeypatch.setenv("RIFFNEL_APPROVERS", "alice,bob")
    with pytest.raises(PermissionError, match="RIFFNEL_APPROVERS"):
        service.approve(w, pid, "mallory")
    monkeypatch.setenv("RIFFNEL_FOUR_EYES", "1")
    monkeypatch.setenv("RIFFNEL_APPROVERS", "alice,drafter")
    with pytest.raises(PermissionError, match="four-eyes"):
        service.approve(w, pid, "drafter")
    service.approve(w, pid, "alice")
    assert w.state()["plans"][pid]["approved_by"] == "alice"


# --- 3. a failed apply can be resumed or rolled back --------------------------------------------------------
def test_partial_apply_is_journaled_resumable_and_rollbackable(tmp_path, monkeypatch):
    w = ws(tmp_path)
    pid = stale_plan(w)
    service.approve(w, pid, "t")
    real_add = JsonFileStore.add

    def failing_add(self, record):
        raise OSError("disk full")

    monkeypatch.setattr(JsonFileStore, "add", failing_add)
    with pytest.raises(OSError):
        service.apply(w, pid)
    p = json.loads((w.root / "state.json").read_text(encoding="utf-8"))["plans"][pid]  # what is on disk, not in memory
    assert p["status"] == "apply_failed" and p["journal"] == [0]  # the first action (invalidate) was done
    assert w.store.get("m_gold_waiver").status == "invalidated"
    assert any(e[3].startswith("apply_failed") for e in w.audit.events())
    monkeypatch.setattr(JsonFileStore, "add", real_add)
    service.apply(w, pid)  # resume
    p = w.state()["plans"][pid]
    assert p["status"] == "applied" and p["journal"] == list(range(len(p["actions"])))
    news = [r for r in w.store.list() if r.supersedes == "m_gold_waiver"]
    assert len(news) == 1  # resumed without duplicating the replacement
    assert all(v["passed"] for v in service.verify(w, pid, []).values())


def test_rollback_of_a_partial_apply_undoes_only_what_was_done(tmp_path, monkeypatch):
    w = ws(tmp_path)
    pid = stale_plan(w)
    service.approve(w, pid, "t")
    monkeypatch.setattr(JsonFileStore, "add", lambda self, r: (_ for _ in ()).throw(OSError("boom")))
    with pytest.raises(OSError):
        service.apply(w, pid)
    service.rollback(w, pid, "t")
    assert w.store.get("m_gold_waiver").status == "active" and w.state()["plans"][pid]["status"] == "rolled_back"


# --- 4. concurrent commands and interrupted writes ----------------------------------------------------------
def test_concurrent_commands_do_not_lose_updates(tmp_path):
    """Each worker reads the state, pauses inside the transaction to force an overlap, then adds one incident.
    Without the lock every worker would see an empty state and they would overwrite each other."""
    w = ws(tmp_path)
    code = ("import sys, time\nfrom riffnel_memguard.core.workspace import Workspace\n"
            "w = Workspace(sys.argv[1])\nwith w.transaction() as st:\n    n = len(st['incidents'])\n    time.sleep(0.25)\n"
            "    st['incidents'][f'inc_{n + 1:03d}'] = {'by': sys.argv[2]}\n")
    procs = [subprocess.Popen([sys.executable, "-c", code, str(w.root), str(i)], stderr=subprocess.PIPE) for i in range(6)]
    for p in procs:
        assert p.wait(timeout=120) == 0, p.stderr.read().decode()
    incidents = w.state()["incidents"]
    assert sorted(incidents) == [f"inc_{i:03d}" for i in range(1, 7)] and len({v["by"] for v in incidents.values()}) == 6


def test_lock_times_out_instead_of_hanging(tmp_path):
    lock = tmp_path / "x.lock"
    held, release = threading.Event(), threading.Event()

    def holder():
        with locking.file_lock(lock):
            held.set()
            release.wait(5)

    t = threading.Thread(target=holder)
    t.start()
    held.wait(5)
    try:
        with pytest.raises(locking.LockTimeout, match="another riffnel-memguard command"):
            with locking.file_lock(lock, timeout=0.3):
                pass
    finally:
        release.set()
        t.join()


def test_an_interrupted_write_never_corrupts_the_state(tmp_path, monkeypatch):
    w = ws(tmp_path)
    before = (w.root / "state.json").read_text(encoding="utf-8")
    monkeypatch.setattr(os, "replace", lambda *a: (_ for _ in ()).throw(OSError("crash before rename")))
    with pytest.raises(OSError):
        w.save_state({"incidents": {"broken": {}}, "plans": {}, "erasures": {}, "verifications": {}})
    monkeypatch.undo()
    assert (w.root / "state.json").read_text(encoding="utf-8") == before  # old file intact
    assert not [f for f in w.root.iterdir() if f.name.endswith(".tmp")]  # no stray temporary file


# --- 5. audit chain: HMAC and head ------------------------------------------------------------------------
def _rewrite_chain(db):
    """What an attacker with write access but no key can do: edit an event and recompute every hash."""
    log = AuditLog(db)
    rows = log.events()
    prev = "0" * 64
    with sqlite3.connect(db) as c:
        for seq, ts, actor, action, ot, oid, psha, _p, _h in rows:
            if seq == 2:
                oid = "forged"
            h = AuditLog._hash(prev, seq, ts, actor, action, ot, oid, psha)
            c.execute("UPDATE audit_events SET object_id=?, prev_hash=?, hash=? WHERE seq=?", (oid, prev, h, seq))
            prev = h


def test_signed_audit_log_detects_a_full_chain_rewrite(tmp_path):
    db = tmp_path / "a.db"
    log = AuditLog(db, key="secret")
    for i in range(3):
        log.append("u", "act", "memory", f"m{i}", "h")
    assert log.verify() == (True, None) and log.signed
    _rewrite_chain(db)
    assert AuditLog(db).verify() == (True, None)  # without the key the rewrite is invisible: documented weakness
    assert AuditLog(db, key="secret").verify()[0] is False  # with the key it is detected
    assert AuditLog(db, key="wrong").verify()[0] is False


def test_unsigned_chain_and_legacy_database(tmp_path):
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as c:  # the schema before the mac column existed
        c.execute("CREATE TABLE audit_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, actor TEXT, action TEXT,"
                  "object_type TEXT, object_id TEXT, payload_sha256 TEXT, prev_hash TEXT, hash TEXT)")
    log = AuditLog(db)  # migrates
    log.append("u", "a", "memory", "m1")
    assert log.verify() == (True, None) and not log.signed
    seq, h = log.head()
    assert seq == 1 and len(h) == 64
    assert AuditLog(db, key="k").verify()[0] is False  # a key was supplied but the events were never signed


def test_cli_audit_commands(tmp_path, monkeypatch):
    w = ws(tmp_path)
    monkeypatch.setenv("RIFFNEL_AUDIT_KEY", "k")
    pid = stale_plan(w)
    service.approve(w, pid, "t")
    r = run(app, ["audit", "verify", str(w.root / "audit.db")])
    assert r.exit_code == 0 and "HMAC" in r.output
    monkeypatch.delenv("RIFFNEL_AUDIT_KEY")
    assert "仅哈希链" not in run(app, ["audit", "verify", str(w.root / "audit.db")]).output  # signed, key not supplied
    assert re.fullmatch(r"\d+ [0-9a-f]{64}\n?", run(app, ["audit", "head", str(w.root / "audit.db")]).output)


def test_erase_reads_targets_from_a_file(tmp_path):
    base = ["--ws", str(tmp_path / "ws")]
    run(app, ["init", *base])
    run(app, ["simulate-delete", "m_phone_raw", *base])
    f = tmp_path / "targets.txt"
    f.write_text("13800000000\n\n", encoding="utf-8")
    r = run(app, ["erase", "--subject", "user=u_demo", "--target-file", str(f), *base])
    assert r.exit_code == 0 and "发现 1 处残留" in r.output
    assert run(app, ["erase", "--subject", "user=u_demo", *base]).exit_code != 0  # no target at all is an error
    assert run(app, ["erase", "--subject", "user=u_demo", "--target-file", str(tmp_path / "nope"), *base]).exit_code != 0
