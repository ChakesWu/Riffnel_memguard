"""Evidence report (Markdown). Personal data is masked; erased content is never printed."""
from __future__ import annotations

import re

from .. import __version__
from ..i18n import tr
from ..probes.erasure import mask

_LONG_NUM = re.compile(r"\d[\d ]{6,}\d")


_EMAIL = re.compile(r"([\w.+-])[\w.+-]*@([\w-]+(?:\.[\w-]+)+)")


def mask_text(text: str) -> str:
    """Mask long digit runs (phone, card and id numbers) and e-mail addresses."""
    text = _LONG_NUM.sub(lambda m: mask(m.group(0).replace(" ", "")), text)
    return _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)


def build(plan: dict, state: dict, events: list[tuple], lang: str = "zh") -> str:
    """The evidence report in Chinese ('zh'), English ('en') or Brazilian Portuguese ('pt')."""
    t = lambda zh, **kw: tr(lang, zh, **kw)  # noqa: E731
    ok = lambda b: t("通过") if b else t("失败")  # noqa: E731
    inc = state["incidents"].get(plan.get("incident_id") or "")
    er = state["erasures"].get(plan.get("erasure_id") or "")
    ver = state["verifications"].get(plan["id"], {})
    L = [f"# {t('证据报告 {id}', id=plan['id'])}", "",
         f"Riffnel_memguard {__version__}　" + t("状态：{s}　审批人：{a}", s=plan["status"], a=plan.get("approved_by") or "—"), ""]
    L += [f"## {t('1. 摘要')}", ""]
    classes = sorted({f["cls"] for f in plan["findings"]})
    L.append(t("- 发现：{n} 条（类别 {c}）", n=len(plan["findings"]), c=", ".join(classes) or t("无")))
    L.append(t("- 修正动作：{n} 个", n=len(plan["actions"])))
    L.append(t("- 验证：{v}", v="；".join(f"{k}={ok(v['passed'])}" for k, v in ver.items())) if ver else t("- 验证：尚未执行"))
    L += ["", f"## {t('2. 事故 / 请求')}", ""]
    if inc:
        L += [t("- 时间：{t}　作用域：{s}", t=inc["occurred_at"], s=inc["scope"]), t("- 问：{q}", q=mask_text(inc["question"])),
              t("- 答：{a}", a=mask_text(inc["answer"]))]
    elif er:
        L += [t("- 删除请求 {id}：对象 {s}，目标（已遮罩）{t}", id=er["id"], s=er["subject"], t=er["targets_masked"])]
    L += ["", f"## {t('3. 证据')}", ""]
    for f in plan["findings"]:
        ev = f["evidence"]
        L.append(t("- **{c}** 记忆 `{m}`（置信度 {conf}）", c=f["cls"], m=f["memory_id"], conf=f["confidence"]))
        if ev.get("language"):
            L.append(t("  - 语言：{l}", l=ev["language"]))
        if "memory_text" in ev:
            L.append(t("  - 记忆原文：{t}", t=mask_text(ev["memory_text"])))
        if "valid_text" in ev:
            L.append(t("  - 当时有效条款（{v}）：{t}", v=ev["valid_version"], t=ev["valid_text"]))
        if "stale_version" in ev:
            L.append(t("  - 记忆对应旧版本：{v}", v=ev["stale_version"]))
        if ev.get("rules"):
            L.append(t("  - 外部扫描（{src} {ver}，严重度 {sev}）：{r}", src=ev.get("source"), ver=ev.get("memwall_version"),
                       sev=ev.get("severity"), r="; ".join(ev["rules"])))
        if ev.get("match"):
            L.append(t("  - 残留匹配方式：{m}；目标 {t}", m=ev["match"], t=ev["targets_masked"]))
    L += ["", f"## {t('4. 修正方案')}", ""]
    for a in plan["actions"]:
        extra = f" → {mask_text(a['payload']['record']['content'])}" if a["type"] == "add" else ""
        L.append(f"- {a['type']} `{a['target']}`{extra}")
    L += ["", f"## {t('5. 验证')}", ""]
    if "replay" in ver:
        L.append(t("- 重放：{r}；回答：{a}", r=ok(ver["replay"]["passed"]), a=mask_text(ver["replay"]["answer"])))
    if "regression" in ver:
        r = ver["regression"]
        L.append(t("- 回归：{r}（受影响 {a}，未受影响 {u}）", r=ok(r["passed"]), a=r["affected"], u=r["unaffected"]))
        L += [f"  - {c['id']}：{ok(c['passed'])}" for c in r["cases"]]
    if "erasure" in ver:
        e = ver["erasure"]
        L.append(t("- 残留探测：{r}（L1={l1} L2={l2} L4={l4}）", r=t("硬性关卡均无命中") if e["passed"] else t("仍有残留"),
                   l1=e["L1_exact"], l2=e["L2_variant"], l4=e["L4_behavior"]))
        if e["L3_semantic"]:
            L.append(t("- 语义层（L3）提示，待人工复核：{items}", items=[i for i, _ in e["L3_semantic"]]))
    if "crosslingual" in ver:
        cl = ver["crosslingual"]
        L.append(t("- 跨语言一致性：{r}", r=ok(cl["passed"])))
        for c in cl["checks"]:
            vals = ", ".join(f"{x['lang']}={x['value']}{'✓' if x['correct'] else '✗'}" for x in c["results"])
            L.append(t("  - {id}（应为 {e}）：{vals}", id=c["check_id"], e=c["expected"], vals=vals))
    L += ["", f"## {t('6. 可重现信息')}", ""]
    L += [t("- 修正前快照 SHA-256：`{h}`", h=plan.get("snapshot_before") or "—"),
          t("- 修正后快照 SHA-256：`{h}`", h=plan.get("snapshot_after") or "—"),
          t("- 生效日期（as_of）：{d}", d=plan.get("as_of")), t("- 检索：字符 2–3 gram TF-IDF，确定性，无随机性；无 LLM")]
    L += ["", f"## {t('7. 审计链')}", ""]
    for seq, ts, actor, action, ot, oid, psha, prev, h in events:
        L.append(f"- #{seq} {ts} {actor} {action} {ot}:{oid} `{h[:12]}`")
    L += ["", t("校验：`riffnel-memguard audit verify <ws>/audit.db`"), ""]
    return "\n".join(L)
