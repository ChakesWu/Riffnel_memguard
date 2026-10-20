"""Run the simulated benchmark and render the results. Every number comes from this run."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from . import __version__
from .adapters.base import JsonFileStore
from .agent.bank import BankAssistAgent
from .core.audit import AuditLog
from .core.models import Clause, Incident, MemoryRecord, TestCase
from .adapters.base import similarity
from .engines import corrector, investigator, linker, verifier


def _store(case, tmp: Path) -> JsonFileStore:
    s = JsonFileStore(tmp / "m.json")
    for m in case["memories"]:
        s.add(MemoryRecord(**m))
    return s


def run_incident(case, tmp: Path) -> dict:
    store, audit = _store(case, tmp), AuditLog(tmp / "a.db")
    clauses = [Clause(**c) for c in case["clauses"]]
    tests = [TestCase(**t) for t in case["tests"]]
    i = case["incident"]
    inc = Incident(id=case["id"], occurred_at=i["occurred_at"], agent_id="bench", scope=i["scope"],
                   question=i["question"], answer=i["answer"], retrieved_ids=i["retrieved"])
    findings = investigator.investigate(inc, store, clauses)
    exp = case["expect"]
    r = {"id": case["id"], "kind": case["kind"], "classes": [f.cls for f in findings], "ids": [f.memory_id for f in findings]}
    if exp["cls"] is None:
        r["no_false_alarm"] = not findings
        return r
    r["attributed"] = set(exp["ids"]) <= set(r["ids"])
    r["class_ok"] = set(r["classes"]) == {exp["cls"]}
    if case["kind"].startswith("M1"):
        links, _ = linker.link(store, clauses)
        r["link_ok"] = any(l.memory_id == "m_bad" and l.clause_version_id == "cv_0_1" for l in links)
    agent = BankAssistAgent(store)
    pre = {t["id"] for t in verifier.regression(agent, tests, set())["cases"] if t["passed"]}
    by_key = {c.key: c for c in clauses}
    plan = corrector.make_plan(findings, store, case["id"], by_key, case["as_of"])
    corrector.approve(plan, "bench", audit)
    corrector.apply(plan, store, audit)
    ans, retrieved = agent.answer(inc.question, inc.scope)
    rep = verifier.replay(agent, inc, clauses, case["as_of"])
    cur = by_key[case["target_key"]].version_at(case["as_of"])
    if case["strict_replay"]:
        r["replay_ok"] = rep["passed"]
    else:
        r["replay_ok"] = not rep["problems"] and exp.get("not_retrieved") not in retrieved
    reg = verifier.regression(agent, tests, set())
    post = {t["id"] for t in reg["cases"] if t["passed"]}
    r["no_degradation"] = pre <= post
    for mid in exp.get("invalidated", []):
        r["derived_purged"] = store.get(mid).status == "invalidated"
    for mid, sc in exp.get("rescoped", {}).items():
        r["rescoped_ok"] = store.get(mid).scope == sc
    r["audit_ok"] = audit.verify()[0]
    return r


def run_erasure(case, tmp: Path) -> dict:
    store, audit = _store(case, tmp), AuditLog(tmp / "a.db")
    for mid in case["upstream_delete"]:
        store.delete(mid)
    agent = BankAssistAgent(store)
    args = (case["subject"], case["targets"], case["description"], case["questions"])
    pre = verifier.erasure(store, agent, *args[:1], *args[1:])
    exp = case["expect"]
    r = {"id": case["id"], "kind": case["kind"], "hard": case["hard"], "l3_flag": bool(pre["L3_semantic"]),
         "layers": [k for k in ("L1_exact", "L2_variant", "L3_semantic", "L4_behavior") if pre[k]]}
    findings = investigator.investigate_erasure(store, case["targets"])
    r["located"] = sorted(f.memory_id for f in findings)
    live = [m.content for m in store.list() if m.status != "deleted"]
    r["l3_max"] = round(max(similarity(case["description"], live)), 3) if live else 0.0
    if not exp["detect"]:
        r["no_false_alarm"] = pre["clean"]
        return r
    r["detected"] = not pre["clean"]
    r["located_ok"] = set(exp["residue"]) <= set(r["located"])
    plan = corrector.make_plan(findings, store, None, {}, "")
    corrector.approve(plan, "bench", audit)
    corrector.apply(plan, store, audit)
    r["clean_after"] = verifier.erasure(store, agent, *args[:1], *args[1:])["clean"]
    return r


def run(cases_path: Path) -> dict:
    cases = json.loads(Path(cases_path).read_text(encoding="utf-8"))
    rows = []
    for c in cases:
        with tempfile.TemporaryDirectory() as d:
            fn = run_erasure if c["kind"].startswith("ERASURE") else run_incident
            row = fn(c, Path(d))
            row["hard"] = c.get("hard", False)
            rows.append(row)
    return {"version": __version__, "n_cases": len(cases), "rows": rows}


def _rate(rows, key):
    rs = [r for r in rows if key in r]
    ok = sum(bool(r[key]) for r in rs)
    return f"{ok}/{len(rs)} ({100 * ok / len(rs):.0f}%)" if rs else "—"


def render(res: dict) -> str:
    rows = res["rows"]
    inc = [r for r in rows if not r["kind"].startswith("ERASURE")]
    er = [r for r in rows if r["kind"].startswith("ERASURE")]
    easy = [r for r in er if not r["hard"]]
    hard = [r for r in er if r["hard"]]
    near = [r for r in er if r["kind"].endswith("NEARMISS")]
    L = ["# 基准结果（仿真）", "",
         f"Riffnel_memguard {res['version']}，{res['n_cases']} 个用例；由 `riffnel-memguard benchmark` 生成，数字均来自该次运行。", "",
         "**读数前提：** 数据为仿真，由项目维护者自行设计；事故回答由有问题的记忆脚本化生成（只有修正后的重放用真实检索）。"
         "样本很小，这些数字说明流程在这些设计好的情形下能否走通，**不代表真实环境的准确率**。", "",
         "## 事故类（调查 → 修正 → 验证）", "", "| 指标 | 结果 |", "|---|---|",
         f"| 归因：责任记忆被找到 | {_rate(inc, 'attributed')} |",
         f"| 分类：类别完全正确 | {_rate(inc, 'class_ok')} |",
         f"| 误报：无错用例（含无法归因）未产生发现 | {_rate(inc, 'no_false_alarm')} |",
         f"| 溯源：过期记忆被链接到正确的旧版本（M1 类） | {_rate(inc, 'link_ok')} |",
         f"| 修正后重放通过 | {_rate(inc, 'replay_ok')} |",
         f"| 回归无退化（修正前通过的题仍通过） | {_rate(inc, 'no_degradation')} |",
         f"| 派生摘要被清理 | {_rate(inc, 'derived_purged')} |",
         f"| 串用记忆被改回正确作用域 | {_rate(inc, 'rescoped_ok')} |",
         f"| 审计链校验通过 | {_rate(inc, 'audit_ok')} |", "",
         "### 分类别", "", "| 类别 | 归因 | 分类 | 重放 | 误报检查 |", "|---|---|---|---|---|"]
    for k in sorted({r["kind"] for r in inc}):
        g = [r for r in inc if r["kind"] == k]
        L.append(f"| {k}（{len(g)}） | {_rate(g, 'attributed')} | {_rate(g, 'class_ok')} | {_rate(g, 'replay_ok')} | {_rate(g, 'no_false_alarm')} |")
    pos = [r for r in er if "located_ok" in r]
    neg = [r for r in er if "no_false_alarm" in r]
    L += ["", "## 删除残留探测", "",
          "L1 精确、L2 变形、L4 行为为硬性关卡；L3 语义层只提示「待人工复核」，不单独决定是否通过。", "",
          "| 指标 | 结果 |", "|---|---|",
          f"| 召回：有残留的用例被硬性关卡探测到（常规） | {_rate(easy, 'detected')} |",
          f"| 定位：残留记录被准确指出（常规） | {_rate(easy, 'located_ok')} |",
          f"| 修正后硬性关卡均无命中（常规） | {_rate(easy, 'clean_after')} |",
          f"| 误报：无残留用例（含近似号码）被硬性关卡误判有残留 | {_rate(er, 'no_false_alarm')} |",
          f"| 困难用例（中文数字、邮箱混淆）被探测到 | {_rate(hard, 'detected')} |",
          f"| 困难用例残留被准确定位 | {_rate(hard, 'located_ok')} |",
          f"| L3 提示：有残留的用例 | {sum(r['l3_flag'] for r in pos)}/{len(pos)} |",
          f"| L3 提示：无残留的用例（即 L3 的误报） | {sum(r['l3_flag'] for r in neg)}/{len(neg)} |"]
    if near:
        L.append(f"| 近似号码用例（{len(near)} 个）L3 最高得分范围（阈值 0.4） | "
                 f"{min(r['l3_max'] for r in near):.2f}–{max(r['l3_max'] for r in near):.2f} |")
    L.append("")
    bad = []
    for r in rows:
        fails = [k for k in ("link_ok", "attributed", "class_ok", "no_false_alarm", "replay_ok", "no_degradation", "derived_purged",
                             "rescoped_ok", "audit_ok", "detected", "located_ok", "clean_after") if k in r and not r[k]]
        if fails:
            bad.append(f"- `{r['id']}`{'（困难）' if r['hard'] else ''}：未通过 {', '.join(fails)}；"
                       f"发现类别 {r.get('classes', r.get('layers'))}")
    L += ["## 未通过的用例", ""] + (bad or ["无"]) + [""]
    return "\n".join(L)
