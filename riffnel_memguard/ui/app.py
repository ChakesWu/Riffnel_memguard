"""Streamlit web UI (black and white, Chinese / English / Português). Run with: riffnel-memguard ui"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import streamlit as st

from riffnel_memguard import service
from riffnel_memguard.agent.command import AgentCommandError
from riffnel_memguard.core.workspace import Workspace
from riffnel_memguard.i18n import LANGS, tr
from riffnel_memguard.report.markdown import mask_text

CSS = """
<style>
html, body, [class*="css"] { font-family: -apple-system, "Noto Sans CJK SC", sans-serif; }
.stApp { background: #ffffff; color: #111111; }
h1, h2, h3 { color: #111111; font-weight: 700; }
div.stButton > button { background: #111111; color: #ffffff; border: 1px solid #111111; border-radius: 2px; }
div.stButton > button:hover { background: #ffffff; color: #111111; }
section[data-testid="stSidebar"] { background: #f2f2f2; }
</style>
"""

# form defaults matching the example data of each example
DEFAULTS = {
    "bank": dict(q="金卡免年费需要刷几笔？", scope="product=gold_card", at="2026-08-10"),
    "bank_br": dict(q="Quantas compras por ano são necessárias para isentar a anuidade do cartão Ouro?",
                    scope="product=ouro_card", at="2026-08-10"),
}
LANG_NAMES = {"zh": "中文", "en": "English", "pt": "Português"}


def lang() -> str:
    return st.session_state.get("lang", "zh")


def T(zh: str, **kw) -> str:
    return tr(lang(), zh, **kw)


def workspace() -> Workspace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", default=os.environ.get("RIFFNEL_WS", ".riffnel"))
    args, _ = ap.parse_known_args()
    return Workspace(Path(args.ws))


def guarded(fn, *a):
    try:
        return fn(*a)
    except (KeyError, ValueError, PermissionError, AgentCommandError) as e:
        st.error(str(e).strip("'"))
        return None


def external_allowed() -> bool:
    """Running a command typed into a web page is remote code execution for anyone who can reach the page, so it is
    off unless the operator sets RIFFNEL_UI_ALLOW_AGENT_CMD=1 (only do this on a trusted, local deployment)."""
    return os.environ.get("RIFFNEL_UI_ALLOW_AGENT_CMD") == "1"


def agent_settings() -> tuple[str | None, float]:
    """Sidebar: the external agent command used for new questions and for probes. Returns (command, timeout)."""
    st.sidebar.markdown("**" + T("外部智能体（可选）") + "**")
    if not external_allowed():
        st.sidebar.caption(T("Web 界面默认不执行外部命令（防止远程执行）。在本机可信环境设置 "
                             "RIFFNEL_UI_ALLOW_AGENT_CMD=1 后启用；命令行 `--agent-cmd` 不受此限制。"))
        return None, 60.0
    cmd = st.sidebar.text_input(T("命令（留空使用内置示例智能体）"), key="agent_cmd",
                                help=T("协议见 README：标准输入一行 JSON，标准输出最后一行 JSON"))
    timeout = st.sidebar.number_input(T("每次调用超时（秒）"), min_value=1.0, value=60.0, key="agent_timeout")
    return (cmd.strip() or None), float(timeout)


def agent_settings_cache() -> tuple[str | None, float]:
    if not external_allowed():
        return None, 60.0
    cmd = (st.session_state.get("agent_cmd") or "").strip() or None
    return cmd, float(st.session_state.get("agent_timeout", 60.0))


def example_kind(w: Workspace) -> str:
    try:
        return "bank_br" if any(c.key.startswith("cartao.") for c in w.clauses) else "bank"
    except (OSError, ValueError):
        return "bank"


def show_crosslingual(checks: list[dict]) -> None:
    """The per-language answers of cross-lingual checks (dicts from a result or a stored verification)."""
    for c in checks:
        st.markdown(f"**{c['check_id']}** · " + T("应为 {v}", v=c["expected"]))
        st.dataframe([{T("语言"): r["lang"], T("答案"): mask_text(r["answer"]), T("数字"): r["value"],
                       T("正确"): "✓" if r["correct"] else ("✗" if r["correct"] is False else "?")}
                      for r in c["results"]], use_container_width=True, hide_index=True)
        if c["passed"]:
            st.success(T("各语言一致且正确"))
        else:
            st.error(T("不一致：{langs} 与有效条款不符", langs=", ".join(c["outliers"])))


def plan_panel(w: Workspace, plan_id: str) -> None:
    state = w.state()
    p = state["plans"][plan_id]
    st.subheader(T("修正方案 {plan_id}　状态：{status}", plan_id=plan_id, status=p["status"]))
    st.code("\n".join(mask_text(x) for x in service.diff(w, plan_id)), language="text")
    c1, c2, c3, c4 = st.columns(4)
    by = st.text_input(T("审批人"), key=f"by_{plan_id}")
    if c1.button(T("审批"), key=f"approve_{plan_id}") and by:
        if guarded(service.approve, w, plan_id, by) is None and service.get_plan(w.state(), plan_id)["status"] == "approved":
            st.rerun()
    if c2.button(T("应用"), key=f"apply_{plan_id}"):
        summary = guarded(service.apply, w, plan_id)
        if summary is not None:
            if summary["targets_pending"]:
                st.session_state["scrub_note"] = T("已清除工作区状态中含目标值的 {n} 处文本，删除含目标值的报告 {m} 份。",
                                                   n=summary["scrubbed_strings"], m=len(summary["reports_removed"]))
            st.rerun()
        elif service.get_plan(w.state(), plan_id)["status"] == "apply_failed":
            st.warning(T("应用中途失败，方案处于 apply_failed。修复原因后再次点击「应用」会从断点继续，或点击「回滚」撤销已完成的部分。"))
    if c3.button(T("验证"), key=f"verify_{plan_id}"):
        stored = state["incidents"].get(p.get("incident_id") or "", {}).get("agent_cmd")
        cmd, timeout = agent_settings_cache()
        if (stored or cmd) and not external_allowed():
            st.warning(T("该方案的验证需要执行外部智能体命令，Web 界面默认不执行（设置 RIFFNEL_UI_ALLOW_AGENT_CMD=1 启用，"
                         "或改用命令行 verify）。"))
        else:
            guarded(service.verify, w, plan_id, ["我的手机号是多少？"], cmd, timeout if cmd else None)
            st.rerun()
    if c4.button(T("回滚"), key=f"rollback_{plan_id}") and by:
        skipped = guarded(service.rollback, w, plan_id, by)
        if skipped is not None:
            st.info(T("无法回滚的删除：{skipped}", skipped=skipped) if skipped else T("已回滚"))
    if st.session_state.get("scrub_note"):
        st.info(st.session_state["scrub_note"])
    er_id = p.get("erasure_id")
    if er_id and w.get_secret(er_id):
        st.caption(T("目标值暂存在工作区 secrets/（权限 0600），验证通过后自动清除。"))
        if st.button(T("丢弃目标值（不再验证）"), key=f"discard_{plan_id}"):
            service.erase_discard(w, er_id)
            st.rerun()
    ver = state["verifications"].get(plan_id, {})
    for k, v in ver.items():
        (st.success if v["passed"] else st.error)(f"{k}: " + (T("通过") if v["passed"] else T("失败")))
        if v.get("needs_review"):
            st.warning(T("语义层（L3）提示，待人工复核：{items}", items=[i for i, _ in v["L3_semantic"]]))
        if k == "crosslingual":
            show_crosslingual(v["checks"])
    if st.button(T("生成证据报告"), key=f"report_{plan_id}"):
        out = service.report(w, plan_id, lang())
        st.download_button(T("下载 Markdown 报告"), out.read_text(encoding="utf-8"), file_name=out.name,
                           key=f"dl_{plan_id}")
        st.markdown(out.read_text(encoding="utf-8"))


def page_overview(w: Workspace) -> None:
    st.header(T("总览"))
    state = w.state()
    st.write(T("记忆 {m} 条　事故 {i} 个　方案 {p} 个", m=len(w.store.list()), i=len(state["incidents"]), p=len(state["plans"])))
    st.dataframe([{"id": r.id, T("状态"): r.status, T("类型"): r.kind, T("作用域"): str(r.scope),
                   T("内容"): mask_text(r.content)} for r in w.store.list()], use_container_width=True)
    if state["plans"]:
        st.subheader(T("方案"))
        st.dataframe([{"id": k, T("状态"): v["status"], T("发现"): ",".join(f["cls"] for f in v["findings"])}
                      for k, v in state["plans"].items()], use_container_width=True)


def page_incident(w: Workspace) -> None:
    d = DEFAULTS[example_kind(w)]
    st.header(T("事故调查"))
    with st.form("ask"):
        q = st.text_input(T("问题"), d["q"])
        sc = st.text_input(T("作用域 (key=value, 逗号分隔)"), d["scope"])
        at = st.text_input(T("事故日期"), d["at"])
        if st.form_submit_button(T("提问并记录事故")):
            cmd, timeout = agent_settings_cache()
            iid = guarded(service.ask, w, q, service._parse_scope([x.strip() for x in sc.split(",") if x.strip()]),
                          at, cmd, timeout)
            if iid:
                st.session_state["iid"] = iid
    incidents = w.state()["incidents"]
    if not incidents:
        return
    iid = st.selectbox(T("事故"), list(incidents), index=list(incidents).index(st.session_state.get("iid", list(incidents)[-1])))
    inc = incidents[iid]
    st.caption(T("智能体：") + (T("外部命令 `{cmd}`", cmd=inc["agent_cmd"]) if inc.get("agent_cmd") else T("内置示例智能体")))
    st.write(T("问：{q}", q=mask_text(inc["question"])))
    st.write(T("答：{a}　取用记忆：{ids}", a=mask_text(inc["answer"]), ids=inc["retrieved_ids"]))
    if st.button(T("调查")):
        guarded(service.investigate, w, iid)
        st.rerun()
    for f in incidents[iid].get("findings", []):
        ev = f["evidence"]
        st.markdown(f"**{f['cls']}** `{f['memory_id']}`　" + T("置信度 {c}", c=f["confidence"]))
        if "memory_text" in ev:
            st.write(T("记忆：{t}", t=mask_text(ev["memory_text"])))
        if "valid_text" in ev:
            st.write(T("当时有效条款（{v}）：{t}", v=ev["valid_version"], t=ev["valid_text"]))
    if "findings" in incidents[iid] and not incidents[iid]["findings"]:
        st.info(T("无法归因：错误不来自被取用的记忆。"))
    if incidents[iid].get("findings"):
        as_of = st.text_input(T("修正生效日期"), "2026-09-01")
        if st.button(T("生成修正方案")):
            st.session_state["plan"] = guarded(service.plan_incident, w, iid, as_of)
    if st.session_state.get("plan") in w.state()["plans"]:
        plan_panel(w, st.session_state["plan"])


def page_crosslingual(w: Workspace) -> None:
    st.header(T("跨语言一致性"))
    st.caption(T("同一个事实用多种语言各问一次，比较智能体的回答是否一致、是否与当时有效的条款一致。"))
    if not w.i18n_checks:
        st.info(T("此工作区没有跨语言检查。用 `riffnel-memguard init --example bank_br` 创建巴西示例，或在工作区放入 i18n_checks.json。"))
        return
    as_of = st.text_input(T("以此日期的条款为准"), "2026-09-01", key="x_asof")
    if st.button(T("运行跨语言检查")):
        cmd, timeout = agent_settings_cache()
        out = guarded(service.check_crosslingual, w, as_of, cmd, timeout)
        if out:
            results, fs, pid = out
            st.session_state["x_checks"] = service._results_dump(results)
            st.session_state["x_findings"] = [(f.cls, f.memory_id, f.evidence.get("language"),
                                               f.evidence.get("memory_text", ""), f.confidence) for f in fs]
            st.session_state["xplan"] = pid
    if "x_checks" in st.session_state:
        show_crosslingual(st.session_state["x_checks"])
        if not st.session_state.get("x_findings") and all(c["passed"] for c in st.session_state["x_checks"]):
            st.info(T("各语言答案一致且正确，没有需要修正的。"))
        if st.session_state.get("x_findings"):
            st.subheader(T("责任记忆"))
            for cls, mid, lg, text, conf in st.session_state["x_findings"]:
                st.markdown(f"**{cls}** `{mid}` " + T("（{l}）", l=lg) + "　" + T("置信度 {c}", c=conf))
                st.write(mask_text(text))
    if st.session_state.get("xplan") in w.state()["plans"]:
        plan_panel(w, st.session_state["xplan"])


def page_erasure(w: Workspace) -> None:
    st.header(T("删除请求"))
    with st.form("erase"):
        sub = st.text_input(T("数据主体作用域"), "user=u_demo")
        tgt = st.text_input(T("需消失的值（精确）"), "13800000000")
        desc = st.text_input(T("语义探测描述"), "客户张三的手机号 13800000000")
        if st.form_submit_button(T("登记并查残留")):
            fs, pid = service.erase(w, service._parse_scope([sub]), [tgt], desc)
            st.session_state["eplan"] = pid
            st.info(T("发现 {n} 处残留", n=len(fs)) if fs else T("未发现残留"))
    if st.session_state.get("eplan") in w.state()["plans"]:
        plan_panel(w, st.session_state["eplan"])


def page_revalidate(w: Workspace) -> None:
    st.header(T("来源更新"))
    as_of = st.text_input(T("检查日期"), "2026-09-01")
    if st.button(T("找出依赖旧版本的记忆")):
        fs, pid = service.revalidate(w, as_of)
        st.session_state["rplan"] = pid
        st.info(T("{n} 条记忆过期", n=len(fs)) if fs else T("没有依赖旧版本的有效记忆"))
    if st.button(T("全面体检（过期 / 冲突 / 无来源）")):
        fs, pid = service.scan(w, as_of)
        st.session_state["rplan"] = pid
        st.info(", ".join(f"{f.cls} {f.memory_id}" for f in fs) if fs else T("未发现问题"))
    if st.session_state.get("rplan") in w.state()["plans"]:
        plan_panel(w, st.session_state["rplan"])


def page_audit(w: Workspace) -> None:
    st.header(T("审计链"))
    ok, bad = w.audit.verify()
    (st.success if ok else st.error)(T("校验通过") if ok else T("第 {n} 条异常", n=bad))
    cols = ["seq", T("时间"), T("操作者"), T("动作"), T("对象类型"), T("对象"), T("载荷哈希"), T("前哈希"), T("哈希")]
    st.dataframe([dict(zip(cols, e)) for e in w.audit.events()], use_container_width=True)


PAGES = {"总览": page_overview, "事故调查": page_incident, "跨语言一致性": page_crosslingual, "删除请求": page_erasure,
         "来源更新": page_revalidate, "审计链": page_audit}


def main() -> None:
    st.set_page_config(page_title="Riffnel_memguard", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    default = os.environ.get("RIFFNEL_UI_LANG", "zh")
    codes = [c for c in LANG_NAMES if c in LANGS]
    pick = st.sidebar.selectbox("Language / 语言 / Idioma", codes, format_func=LANG_NAMES.get,
                                index=codes.index(default) if default in codes else 0)
    st.session_state["lang"] = pick
    st.title("Riffnel_memguard")
    st.caption(T("示例数据均为仿真。"))
    w = workspace()
    if not w.initialized:
        st.warning(T("工作区 {root} 尚未初始化", root=w.root))
        if st.button(T("用仿真示例初始化")):
            w.init(True)
            st.rerun()
        if st.button(T("用巴西仿真示例初始化（中/葡/英）")):
            w.init("bank_br")
            st.rerun()
        return
    choice = st.sidebar.radio(T("页面"), list(PAGES), format_func=T)
    agent_settings()
    PAGES[choice](w)


main()
