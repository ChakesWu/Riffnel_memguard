import pytest
from typer.testing import CliRunner

from riffnel_memguard import demo_crosslingual, service
from riffnel_memguard.cli import app
from riffnel_memguard.core.models import Clause, ClauseVersion, MemoryRecord
from riffnel_memguard.core.workspace import Workspace
from riffnel_memguard.engines import crosslingual, linker
from riffnel_memguard.extract.rules import detect_lang, extract_claim

CLAUSE = Clause(id="c", key="k", title="t", unit=["笔", "compras", "purchases"],
                keywords=["金卡免年费", "anuidade do cartão Ouro", "Gold card annual fee"],
                versions=[ClauseVersion(id="v", version="v1", text="x", value=6, valid_from="2025-01-01")])


@pytest.mark.parametrize("text,value", [
    ("金卡免年费需要每年刷满6笔。", 6),
    ("金卡免年费需要每年刷满六笔。", 6),
    ("A anuidade do cartão Ouro é isenta com 6 compras por ano.", 6),
    ("A anuidade do cartão Ouro é isenta com seis compras por ano.", 6),
    ("ANUIDADE DO CARTÃO OURO: isenção com vinte e três compras.", 23),
    ("The Gold card annual fee is waived after twenty-three purchases a year.", 23),
    ("The Gold card annual fee is waived after 6 purchases.", 6),
    ("A anuidade do cartão Ouro é isenta com 1.000 compras", 1000),
    ("The Gold card annual fee is waived after 2,5 purchases", 2.5),
])
def test_claims_are_extracted_in_three_languages(text, value):
    assert extract_claim(text, CLAUSE).value == value


@pytest.mark.parametrize("text", [
    "A anuidade do cartão Ouro é isenta com seiscentos compras",  # hundreds are not supported: no claim rather than a wrong one
    "O cartão Ouro tem 6 compras",                                 # no keyword of the clause
    "A anuidade do cartão Ouro mudou em 2026",                     # no number with the unit
])
def test_no_claim_is_better_than_a_wrong_claim(text):
    assert extract_claim(text, CLAUSE) is None


def test_detect_lang():
    assert (detect_lang("金卡免年费"), detect_lang("A anuidade do cartão Ouro"), detect_lang("The Gold card annual fee")) == ("zh", "pt", "en")


@pytest.fixture
def ws(tmp_path):
    w = Workspace(tmp_path / "ws")
    w.init("bank_br")
    return w


def test_inconsistency_is_found_and_traced_to_the_stale_language_version(ws):
    results, fs, pid = service.check_crosslingual(ws, "2026-09-01")
    waiver = next(r for r in results if r.check_id == "chk_waiver")
    assert waiver.values == {"zh": 6, "pt": 3, "en": 6} and waiver.expected == 6
    assert not waiver.consistent and waiver.outliers == ["pt"]
    assert next(r for r in results if r.check_id == "chk_term").passed  # the unchanged fact is consistent
    assert [(f.cls, f.memory_id, f.evidence["language"]) for f in fs] == [("M1", "m_w_pt", "pt")]
    assert pid


def test_the_replacement_is_written_in_the_language_of_the_stale_memory(ws):
    _, _, pid = service.check_crosslingual(ws, "2026-09-01")
    actions = ws.state()["plans"][pid]["actions"]
    adds = [a for a in actions if a["type"] == "add"]
    assert len(adds) == 1  # zh and en already carry the current value: only Portuguese needs a new memory
    rec = adds[0]["payload"]["record"]
    assert rec["lang"] == "pt" and "6 compras" in rec["content"] and "6笔" not in rec["content"]
    assert {a["target"] for a in actions if a["type"] == "purge_derived"} == {"m_w_pt_sum"}


def test_verification_rechecks_every_language(ws):
    _, _, pid = service.check_crosslingual(ws, "2026-09-01")
    service.approve(ws, pid, "t")
    service.apply(ws, pid)
    ver = service.verify(ws, pid, [])
    assert ver["crosslingual"]["passed"] and ver["regression"]["passed"]
    results, fs, pid2 = service.check_crosslingual(ws, "2026-09-01")
    assert all(r.passed for r in results) and fs == [] and pid2 is None


def test_a_missing_claim_counts_as_inconsistent(ws):
    class Silent:
        """Answers normally except in Portuguese, where it states no number."""
        def answer(self, q, scope):
            if "Quantas" in q:
                return "Não sei.", []
            top = ws.store.search(q, scope, 1)[0][0]
            return top.content, [top.id]

    r = crosslingual.run(Silent(), ws.i18n_checks[:1], ws.clauses, "2026-09-01")[0]
    assert r.values["pt"] is None and not r.consistent and "pt" in r.outliers


def test_semantic_link_uses_the_text_of_the_memorys_language(ws):
    links, unsupported = linker.link(ws.store, ws.clauses)
    by = {l.memory_id: l for l in links}
    assert by["m_w_pt"].clause_version_id == "cv_w1" and by["m_w_pt"].method == "semantic" and by["m_w_pt"].confidence > 0.5
    assert by["m_w_zh"].clause_version_id == "cv_w2" and by["m_w_en"].clause_version_id == "cv_w2"
    assert not [u for u in unsupported if u[0].startswith("m_w")]


def test_scan_finds_the_stale_portuguese_memory_without_any_question(ws):
    fs, pid = service.scan(ws, "2026-09-01")
    assert {f.memory_id for f in fs} == {"m_w_pt", "m_w_pt_sum"} and pid


def test_stale_replacement_in_chinese_is_still_chinese(tmp_path):
    w = Workspace(tmp_path / "ws")
    w.init("bank")
    fs, pid = service.scan(w, "2026-09-01")
    add = next(a for a in w.state()["plans"][pid]["actions"] if a["type"] == "add")
    assert add["payload"]["record"]["lang"] == "zh" and "6笔" in add["payload"]["record"]["content"]


def test_cli_and_demo(tmp_path):
    run = CliRunner().invoke
    base = ["--ws", str(tmp_path / "ws")]
    assert run(app, ["init", "--example", "bank_br", *base]).exit_code == 0
    r = run(app, ["crosslingual", "--as-of", "2026-09-01", *base])
    assert r.exit_code == 0 and "pt=3✗" in r.output and "方案 plan_" in r.output
    assert run(app, ["init", "--example", "nope", *base]).exit_code != 0
    assert run(app, ["init", "--example", "bank", "--ws", str(tmp_path / "w2")]).exit_code == 0
    assert run(app, ["crosslingual", "--as-of", "2026-09-01", "--ws", str(tmp_path / "w2")]).exit_code != 0  # no i18n checks there
    assert demo_crosslingual.run(tmp_path / "demo", log=lambda *_: None)["passed"]
