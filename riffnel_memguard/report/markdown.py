"""Evidence report (Markdown). Personal data is masked; erased content is never printed."""
from __future__ import annotations

import re

from .. import __version__
from ..probes.erasure import mask

_LONG_NUM = re.compile(r"\d[\d ]{6,}\d")


_EMAIL = re.compile(r"([\w.+-])[\w.+-]*@([\w-]+(?:\.[\w-]+)+)")


def mask_text(text: str) -> str:
    """Mask long digit runs (phone, card and id numbers) and e-mail addresses."""
    text = _LONG_NUM.sub(lambda m: mask(m.group(0).replace(" ", "")), text)
    return _EMAIL.sub(lambda m: f"{m.group(1)}***@{m.group(2)}", text)


def build(plan: dict, state: dict, events: list[tuple]) -> str:
    inc = state["incidents"].get(plan.get("incident_id") or "")
    er = state["erasures"].get(plan.get("erasure_id") or "")
    ver = state["verifications"].get(plan["id"], {})
    L = [f"# 证据报告 {plan['id']}", "",
         f"Riffnel_memguard {__version__}　状态：{plan['status']}　审批人：{plan.get('approved_by') or '—'}", ""]
    L += ["## 1. 摘要", ""]
    classes = sorted({f['cls'] for f in plan['findings']})
    L.append(f"- 发现：{len(plan['findings'])} 条（类别 {', '.join(classes) or '无'}）")
    L.append(f"- 修正动作：{len(plan['actions'])} 个")
    if ver:
        L.append("- 验证：" + "；".join(f"{k}={'通过' if v['passed'] else '失败'}" for k, v in ver.items()))
    else:
        L.append("- 验证：尚未执行")
    L += ["", "## 2. 事故 / 请求", ""]
    if inc:
        L += [f"- 时间：{inc['occurred_at']}　作用域：{inc['scope']}", f"- 问：{mask_text(inc['question'])}",
              f"- 答：{mask_text(inc['answer'])}"]
    elif er:
        L += [f"- 删除请求 {er['id']}：对象 {er['subject']}，目标（已遮罩）{er['targets_masked']}"]
    L += ["", "## 3. 证据", ""]
    for f in plan["findings"]:
        ev = f["evidence"]
        L.append(f"- **{f['cls']}** 记忆 `{f['memory_id']}`（置信度 {f['confidence']}）")
        if "memory_text" in ev:
            L.append(f"  - 记忆原文：{mask_text(ev['memory_text'])}")
        if "valid_text" in ev:
            L.append(f"  - 当时有效条款（{ev['valid_version']}）：{ev['valid_text']}")
        if "stale_version" in ev:
            L.append(f"  - 记忆对应旧版本：{ev['stale_version']}")
        if ev.get("rules"):
            L.append(f"  - 外部扫描（{ev.get('source')} {ev.get('memwall_version')}，严重度 {ev.get('severity')}）：{'; '.join(ev['rules'])}")
        if ev.get("match"):
            L.append(f"  - 残留匹配方式：{ev['match']}；目标 {ev['targets_masked']}")
    L += ["", "## 4. 修正方案", ""]
    for a in plan["actions"]:
        extra = f" → {mask_text(a['payload']['record']['content'])}" if a["type"] == "add" else ""
        L.append(f"- {a['type']} `{a['target']}`{extra}")
    L += ["", "## 5. 验证", ""]
    if "replay" in ver:
        L.append(f"- 重放：{'通过' if ver['replay']['passed'] else '失败'}；回答：{mask_text(ver['replay']['answer'])}")
    if "regression" in ver:
        r = ver["regression"]
        L.append(f"- 回归：{'通过' if r['passed'] else '失败'}（受影响 {r['affected']}，未受影响 {r['unaffected']}）")
        L += [f"  - {c['id']}：{'通过' if c['passed'] else '失败'}" for c in r["cases"]]
    if "erasure" in ver:
        e = ver["erasure"]
        L.append(f"- 残留探测：{'四层均无命中' if e['passed'] else '仍有残留'}"
                 f"（L1={e['L1_exact']} L2={e['L2_variant']} L4={e['L4_behavior']}）")
        if e["L3_semantic"]:
            L.append(f"- 语义层（L3）提示，待人工复核：{[i for i, _ in e['L3_semantic']]}")
    L += ["", "## 6. 可重现信息", ""]
    L += [f"- 修正前快照 SHA-256：`{plan.get('snapshot_before') or '—'}`",
          f"- 修正后快照 SHA-256：`{plan.get('snapshot_after') or '—'}`",
          f"- 生效日期（as_of）：{plan.get('as_of')}", "- 检索：字符 2–3 gram TF-IDF，确定性，无随机性；无 LLM"]
    L += ["", "## 7. 审计链", ""]
    for seq, ts, actor, action, ot, oid, psha, prev, h in events:
        L.append(f"- #{seq} {ts} {actor} {action} {ot}:{oid} `{h[:12]}`")
    L += ["", "校验：`riffnel-memguard audit verify <ws>/audit.db`", ""]
    return "\n".join(L)
