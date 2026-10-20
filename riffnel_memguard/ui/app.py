"""Streamlit web UI (black and white). Run with: riffnel-memguard ui"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import streamlit as st

from riffnel_memguard import service
from riffnel_memguard.core.workspace import Workspace
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


def workspace() -> Workspace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", default=os.environ.get("RIFFNEL_WS", ".riffnel"))
    args, _ = ap.parse_known_args()
    return Workspace(Path(args.ws))


def guarded(fn, *a):
    try:
        return fn(*a)
    except (KeyError, ValueError, PermissionError) as e:
        st.error(str(e).strip("'"))
        return None


def plan_panel(w: Workspace, plan_id: str) -> None:
    state = w.state()
    p = state["plans"][plan_id]
    st.subheader(f"修正方案 {plan_id}　状态：{p['status']}")
    st.code("\n".join(mask_text(x) for x in service.diff(w, plan_id)), language="text")
    c1, c2, c3, c4 = st.columns(4)
    by = st.text_input("审批人", key=f"by_{plan_id}")
    if c1.button("审批", key=f"approve_{plan_id}") and by:
        service.approve(w, plan_id, by)
        st.rerun()
    if c2.button("应用", key=f"apply_{plan_id}"):
        if guarded(service.apply, w, plan_id) is None and service.get_plan(w.state(), plan_id)["status"] == "applied":
            st.rerun()
    if c3.button("验证", key=f"verify_{plan_id}"):
        guarded(service.verify, w, plan_id, ["我的手机号是多少？"])
        st.rerun()
    if c4.button("回滚", key=f"rollback_{plan_id}") and by:
        skipped = service.rollback(w, plan_id, by)
        st.info(f"无法回滚的删除：{skipped}" if skipped else "已回滚")
    ver = state["verifications"].get(plan_id, {})
    for k, v in ver.items():
        (st.success if v["passed"] else st.error)(f"{k}：{'通过' if v['passed'] else '失败'}")
        if v.get("needs_review"):
            st.warning(f"语义层（L3）提示，待人工复核：{[i for i, _ in v['L3_semantic']]}")
    if st.button("生成证据报告", key=f"report_{plan_id}"):
        out = service.report(w, plan_id)
        st.download_button("下载 Markdown 报告", out.read_text(encoding="utf-8"), file_name=out.name,
                           key=f"dl_{plan_id}")
        st.markdown(out.read_text(encoding="utf-8"))


def page_overview(w: Workspace) -> None:
    st.header("总览")
    state = w.state()
    st.write(f"记忆 {len(w.store.list())} 条　事故 {len(state['incidents'])} 个　方案 {len(state['plans'])} 个")
    st.dataframe([{"id": r.id, "状态": r.status, "类型": r.kind, "作用域": str(r.scope),
                   "内容": mask_text(r.content)} for r in w.store.list()], use_container_width=True)
    if state["plans"]:
        st.subheader("方案")
        st.dataframe([{"id": k, "状态": v["status"], "发现": ",".join(f["cls"] for f in v["findings"])}
                      for k, v in state["plans"].items()], use_container_width=True)


def page_incident(w: Workspace) -> None:
    st.header("事故调查")
    with st.form("ask"):
        q = st.text_input("问题", "金卡免年费需要刷几笔？")
        sc = st.text_input("作用域 (key=value, 逗号分隔)", "product=gold_card")
        at = st.text_input("事故日期", "2026-08-10")
        if st.form_submit_button("提问并记录事故"):
            iid = service.ask(w, q, service._parse_scope([x.strip() for x in sc.split(",") if x.strip()]), at)
            st.session_state["iid"] = iid
    incidents = w.state()["incidents"]
    if not incidents:
        return
    iid = st.selectbox("事故", list(incidents), index=list(incidents).index(st.session_state.get("iid", list(incidents)[-1])))
    inc = incidents[iid]
    st.write(f"问：{mask_text(inc['question'])}")
    st.write(f"答：{mask_text(inc['answer'])}　取用记忆：{inc['retrieved_ids']}")
    if st.button("调查"):
        guarded(service.investigate, w, iid)
        st.rerun()
    for f in incidents[iid].get("findings", []):
        ev = f["evidence"]
        st.markdown(f"**{f['cls']}** `{f['memory_id']}`　置信度 {f['confidence']}")
        if "memory_text" in ev:
            st.write(f"记忆：{mask_text(ev['memory_text'])}")
        if "valid_text" in ev:
            st.write(f"当时有效条款（{ev['valid_version']}）：{ev['valid_text']}")
    if "findings" in incidents[iid] and not incidents[iid]["findings"]:
        st.info("无法归因：错误不来自被取用的记忆。")
    if incidents[iid].get("findings"):
        as_of = st.text_input("修正生效日期", "2026-09-01")
        if st.button("生成修正方案"):
            st.session_state["plan"] = guarded(service.plan_incident, w, iid, as_of)
    if st.session_state.get("plan") in w.state()["plans"]:
        plan_panel(w, st.session_state["plan"])


def page_erasure(w: Workspace) -> None:
    st.header("删除请求")
    with st.form("erase"):
        sub = st.text_input("数据主体作用域", "user=u_demo")
        tgt = st.text_input("需消失的值（精确）", "13800000000")
        desc = st.text_input("语义探测描述", "客户张三的手机号 13800000000")
        if st.form_submit_button("登记并查残留"):
            fs, pid = service.erase(w, service._parse_scope([sub]), [tgt], desc)
            st.session_state["eplan"] = pid
            st.info(f"发现 {len(fs)} 处残留" if fs else "未发现残留")
    if st.session_state.get("eplan") in w.state()["plans"]:
        plan_panel(w, st.session_state["eplan"])


def page_revalidate(w: Workspace) -> None:
    st.header("来源更新")
    as_of = st.text_input("检查日期", "2026-09-01")
    if st.button("找出依赖旧版本的记忆"):
        fs, pid = service.revalidate(w, as_of)
        st.session_state["rplan"] = pid
        st.info(f"{len(fs)} 条记忆过期" if fs else "没有依赖旧版本的有效记忆")
    if st.button("全面体检（过期 / 冲突 / 无来源）"):
        fs, pid = service.scan(w, as_of)
        st.session_state["rplan"] = pid
        st.info("、".join(f"{f.cls} {f.memory_id}" for f in fs) if fs else "未发现问题")
    if st.session_state.get("rplan") in w.state()["plans"]:
        plan_panel(w, st.session_state["rplan"])


def page_audit(w: Workspace) -> None:
    st.header("审计链")
    ok, bad = w.audit.verify()
    (st.success if ok else st.error)("校验通过" if ok else f"第 {bad} 条异常")
    st.dataframe([dict(zip(["seq", "时间", "操作者", "动作", "对象类型", "对象", "载荷哈希", "前哈希", "哈希"], e))
                  for e in w.audit.events()], use_container_width=True)


def main() -> None:
    st.set_page_config(page_title="Riffnel_memguard", layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    st.title("Riffnel_memguard")
    st.caption("示例数据均为仿真。")
    w = workspace()
    if not w.initialized:
        st.warning(f"工作区 {w.root} 尚未初始化")
        if st.button("用仿真示例初始化"):
            w.init(True)
            st.rerun()
        return
    pages = {"总览": page_overview, "事故调查": page_incident, "删除请求": page_erasure,
             "来源更新": page_revalidate, "审计链": page_audit}
    choice = st.sidebar.radio("页面", list(pages))
    pages[choice](w)


main()
