"""Parse content.html into a JSON block model for build_docx.js, and render the two SVG figures to PNG."""
from __future__ import annotations

import json
import re
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
OUT = Path("/tmp/intro_docx")
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"


def runs(node, bold=False, code=False) -> list[dict]:
    out: list[dict] = []
    for ch in node.children:
        if isinstance(ch, NavigableString):
            t = re.sub(r"\s+", " ", str(ch))
            if t:
                out.append({"t": t, "b": bold, "c": code})
        elif isinstance(ch, Tag):
            if ch.name in ("b", "strong"):
                out += runs(ch, True, code)
            elif ch.name == "code":
                out += runs(ch, bold, True)
            elif ch.name == "br":
                out.append({"br": True})
            else:
                out += runs(ch, bold, code)
    return out


def table(tag: Tag) -> dict:
    rows = []
    for tr in tag.find_all("tr"):
        cells = []
        for td in tr.find_all(["td", "th"]):
            w = re.search(r"width:\s*(\d+)%", td.get("style", "")) or None
            cells.append({"runs": runs(td), "th": td.name == "th", "w": int(w.group(1)) if w else None,
                          "k": "k" in (td.get("class") or [])})
        rows.append(cells)
    return {"type": "table", "rows": rows, "classes": tag.get("class") or []}


def render_figs(soup) -> list[dict]:
    OUT.mkdir(parents=True, exist_ok=True)
    figs = []
    html = f"<html><body style='margin:0;background:#fff'>{''.join(str(f.find('svg')) for f in soup.select('.fig'))}</body></html>"
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 960, "height": 700}, device_scale_factor=2)
        pg.set_content(html)
        for i, el in enumerate(pg.query_selector_all("svg")):
            path = OUT / f"fig{i + 1}.png"
            el.screenshot(path=str(path))
            box = el.bounding_box()
            figs.append({"path": str(path), "w": int(box["width"]), "h": int(box["height"])})
        b.close()
    return figs


def main() -> None:
    soup = BeautifulSoup((HERE / "content.html").read_text(encoding="utf-8"), "html.parser")
    figs = render_figs(soup)
    blocks: list[dict] = []
    fig_i = 0
    for sec in soup.find_all("section", recursive=False):
        cls = sec.get("class") or []
        if "cover" in cls:
            blocks.append({"type": "cover", "top": runs(sec.select_one(".cover-top")),
                           "title": sec.select_one(".title").get_text(), "subtitle": sec.select_one(".subtitle").get_text(),
                           "subtitle_en": sec.select_one(".subtitle-en").get_text(), "table": table(sec.select_one(".cover-table")),
                           "note": runs(sec.select_one(".cover-note"))})
            continue
        if "toc-page" in cls:
            blocks.append({"type": "toc"})
            continue
        first = True
        for el in sec.children:
            if not isinstance(el, Tag):
                continue
            if el.name == "h1":
                blocks.append({"type": "h1", "text": el.get_text(), "newpage": first and "newpage" in cls})
            elif el.name == "h2":
                blocks.append({"type": "h2", "text": el.get_text()})
            elif el.name == "p":
                c = el.get("class") or []
                blocks.append({"type": "p", "runs": runs(el), "kind": "lead" if "lead" in c else "note" if "note" in c else "p"})
            elif el.name in ("ul", "ol"):
                blocks.append({"type": el.name, "items": [runs(li) for li in el.find_all("li", recursive=False)],
                               "small": "refs" in (el.get("class") or [])})
            elif el.name == "table":
                blocks.append(table(el))
            elif el.name == "div" and "fig" in (el.get("class") or []):
                blocks.append({"type": "fig", **figs[fig_i], "caption": el.select_one(".cap").get_text()})
                fig_i += 1
            first = False
    (OUT / "model.json").write_text(json.dumps(blocks, ensure_ascii=False), encoding="utf-8")
    print(f"{len(blocks)} blocks, {len(figs)} figures -> {OUT/'model.json'}")


if __name__ == "__main__":
    main()
