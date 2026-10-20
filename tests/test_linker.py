from typer.testing import CliRunner

from riffnel_memguard import demo, service
from riffnel_memguard.cli import app
from riffnel_memguard.core.models import Incident, MemoryRecord
from riffnel_memguard.core.workspace import Workspace
from riffnel_memguard.engines import investigator, linker


def ws(tmp_path):
    w = Workspace(tmp_path)
    w.init(True)
    return w


def test_link_methods_and_confidence(tmp_path):
    w = ws(tmp_path)
    w.store.add(MemoryRecord(id="x_explicit", content="任意文字", source_ref="cv_gw_2"))
    links, _ = linker.link(w.store, w.clauses)
    by = {l.memory_id: l for l in links}
    assert (by["x_explicit"].method, by["x_explicit"].confidence, by["x_explicit"].clause_version_id) == ("explicit", 1.0, "cv_gw_2")
    assert (by["m_gold_waiver"].method, by["m_gold_waiver"].clause_version_id) == ("key_match", "cv_gw_1")
    assert by["m_gold_waiver_sum"].method == "semantic" and 0.2 <= by["m_gold_waiver_sum"].confidence < 1


def test_semantic_threshold_leaves_weak_match_unlinked(tmp_path):
    w = ws(tmp_path)
    links, unsupported = linker.link(w.store, w.clauses, threshold=0.9)
    assert "m_gold_waiver_sum" not in {l.memory_id for l in links}
    assert any(u[0] == "m_gold_waiver_sum" and u[3].startswith("low_similarity") for u in unsupported)


def test_value_matching_no_version_is_unsupported(tmp_path):
    w = ws(tmp_path)
    w.store.add(MemoryRecord(id="x", content="金卡免年费需要每年刷满9笔。", scope={"product": "gold_card"}))
    _, unsupported = linker.link(w.store, w.clauses)
    assert ("x", "credit_card.gold.annual_fee.waiver_min_txn", 9, "value_matches_no_version") in unsupported


def test_impact_walks_memories_derived_and_tests(tmp_path):
    w = ws(tmp_path)
    r = service.impact(w, "cv_gw_1")
    assert r["memories"] == ["m_gold_waiver", "m_gold_waiver_sum"] and r["tests"] == ["t_gold_waiver"]
    w.store.add(MemoryRecord(id="m_deep", content="二次摘要", kind="summary", derived_from=["m_gold_waiver_sum"]))
    assert "m_deep" in service.impact(w, "cv_gw_1")["derived"]


def test_conflict_with_authority_invalidates_loser(tmp_path):
    w = ws(tmp_path)
    w.store.add(MemoryRecord(id="m_new", content="金卡免年费需要每年刷满6笔。", scope={"product": "gold_card"},
                             key="credit_card.gold.annual_fee.waiver_min_txn", value=6))
    w.store.add(MemoryRecord(id="m_odd", content="金卡免年费需要每年刷满9笔。", scope={"product": "gold_card"}))
    fs = linker.conflict_findings(w.store, w.clauses, "2026-09-01")
    assert [(f.cls, f.memory_id, f.evidence["authoritative_memory"]) for f in fs] == [("M2", "m_odd", "m_new")]
    # the stale 3-transaction memory is M1's job, not M2's
    assert "m_gold_waiver" not in {f.memory_id for f in fs}


def test_conflict_without_authority_is_quarantined(tmp_path):
    w = ws(tmp_path)
    w.store.get("m_gold_waiver").status = "invalidated"
    for i, v in enumerate((8, 9)):
        w.store.add(MemoryRecord(id=f"c{i}", content=f"金卡免年费需要每年刷满{v}笔。", scope={"product": "gold_card"}))
    fs, pid = service.scan(w, "2026-09-01")
    m2 = [f for f in fs if f.cls == "M2"]
    assert {f.memory_id for f in m2} == {"c0", "c1"} and all(f.evidence["authoritative_memory"] is None for f in m2)
    service.approve(w, pid, "t")
    service.apply(w, pid)
    assert w.store.get("c0").status == "quarantined" and w.store.get("c1").status == "quarantined"


def test_incident_with_authoritative_peer_is_m2_not_m4(tmp_path):
    w = ws(tmp_path)
    w.store.add(MemoryRecord(id="m_new", content="金卡免年费需要每年刷满6笔。", scope={"product": "gold_card"},
                             key="credit_card.gold.annual_fee.waiver_min_txn", value=6))
    w.store.add(MemoryRecord(id="m_odd", content="金卡免年费需要每年刷满9笔。", scope={"product": "gold_card"}))
    inc = Incident(id="i", occurred_at="2026-08-10", agent_id="a", scope={"product": "gold_card"},
                   question="金卡免年费需要刷几笔？", answer="金卡免年费需要每年刷满9笔。", retrieved_ids=["m_odd"])
    assert [f.cls for f in investigator.investigate(inc, w.store, w.clauses)] == ["M2"]


def test_scan_finds_stale_in_example_and_fix_verifies(tmp_path):
    w = ws(tmp_path)
    fs, pid = service.scan(w, "2026-09-01")
    assert {f.memory_id for f in fs} >= {"m_gold_waiver", "m_gold_waiver_sum"}
    service.approve(w, pid, "t")
    service.apply(w, pid)
    assert all(v["passed"] for v in service.verify(w, pid, []).values())
    assert service.scan(w, "2026-09-01")[0] == []  # clean after the fix


def test_cli_link_impact_scan(tmp_path):
    base = ["--ws", str(tmp_path)]
    run = CliRunner().invoke
    assert run(app, ["init", *base]).exit_code == 0
    out = run(app, ["link", *base]).output
    assert "key_match" in out and "semantic" in out
    assert "m_gold_waiver" in run(app, ["impact", "cv_gw_1", *base]).output
    assert run(app, ["impact", "nope", *base]).exit_code != 0
    assert "方案 plan_" in run(app, ["scan", "--as-of", "2026-09-01", *base]).output
