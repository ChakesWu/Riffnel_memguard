"""Build the contest introduction PDF from content.html (black and white, A4, simple lines).

Run: python3 docs/intro/build.py   (needs playwright with a Chromium, and pypdf)
Two passes: the first finds the page of each heading, the second writes the table of contents with page numbers.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright
from pypdf import PdfReader

HERE = Path(__file__).parent
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

CSS = """
@page { size: A4; margin: 22mm 20mm 22mm 20mm; }
* { color: #000; }
html, body { background: #fff; }
body { font-family: "WenQuanYi Zen Hei", "Noto Sans CJK SC", sans-serif; font-size: 10.5pt; line-height: 1.75; margin: 0; }
section { margin: 0; }
section.cover { break-after: page; }
section.toc-page { break-after: page; }
section.newpage { break-before: page; }
h1 { break-after: avoid; font-size: 16pt; font-weight: bold; margin: 22pt 0 10pt 0; padding-bottom: 4pt; border-bottom: 1.2pt solid #000; }
h1.nobreak { margin: 0 0 14pt 0; }
section > h1:first-child { margin-top: 0; }
h2 { break-after: avoid; font-size: 12pt; font-weight: bold; margin: 14pt 0 5pt 0; }
p { margin: 0 0 7pt 0; text-align: justify; }
p.lead { border: 0.75pt solid #000; padding: 6pt 9pt; }
p.note { font-size: 9.5pt; }
ul, ol { margin: 0 0 7pt 0; padding-left: 20pt; }
li { margin-bottom: 2pt; }
code { font-family: "WenQuanYi Zen Hei Mono", monospace; font-size: 9pt; }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 9pt 0; page-break-inside: auto; }
tr { page-break-inside: avoid; }
tr:has(th) { break-after: avoid; }
h2 + table, h2 + p { break-before: avoid; }
th, td { border: 0.6pt solid #000; padding: 3.5pt 6pt; vertical-align: top; text-align: left; font-size: 9.6pt; line-height: 1.55; }
th { font-weight: bold; border-bottom: 1.2pt solid #000; }
table.keep { break-inside: avoid; }
table.small th, table.small td { font-size: 8.8pt; }
table.kv td.k { width: 17%; font-weight: bold; }
.fig { margin: 6pt 0 10pt 0; page-break-inside: avoid; }
.cap { text-align: center; font-size: 9.5pt; margin-top: 3pt; }
.refs li { word-break: break-all; font-size: 8.6pt; line-height: 1.45; margin-bottom: 1pt; }
/* cover */
.cover { padding-top: 38mm; }
.cover-top { font-size: 11pt; margin-bottom: 36mm; }
.title { font-size: 30pt; border: none; margin-bottom: 8pt; padding: 0; }
.subtitle { font-size: 16pt; margin-bottom: 4pt; }
.subtitle-en { font-size: 11pt; margin-bottom: 34mm; }
.cover-table { width: 80%; }
.cover-table td { font-size: 10.5pt; padding: 5pt 8pt; }
.cover-table td:first-child { width: 28%; font-weight: bold; }
.cover-note { font-size: 9pt; margin-top: 14pt; }
/* toc */
#toc .row { display: flex; align-items: baseline; margin: 0 0 6pt 0; font-size: 11pt; }
#toc .row .t { flex: 0 0 auto; }
#toc .row .d { flex: 1 1 auto; border-bottom: 0.6pt dotted #000; margin: 0 4pt; transform: translateY(-3pt); }
#toc .row .p { flex: 0 0 auto; }
#toc .row.sub { padding-left: 16pt; font-size: 10pt; }
"""

HEAD = '<meta charset="utf-8"><title>Riffnel_memguard 作品介绍</title>'


def headings(content: str) -> list[tuple[str, str]]:
    return [(m.group(1), re.sub(r"<[^>]+>", "", m.group(2)))
            for m in re.finditer(r'<h1 id="([^"]+)">(.*?)</h1>', content)]


def toc_html(items, pages) -> str:
    rows = []
    for hid, title in items:
        rows.append(f'<div class="row"><span class="t">{title}</span><span class="d"></span>'
                    f'<span class="p">{pages.get(hid, "")}</span></div>')
    return "\n".join(rows)


def render(page, html: str, out: Path | None) -> None:
    page.set_content(html, wait_until="load")
    if out:
        page.pdf(path=str(out), format="A4", print_background=False, display_header_footer=True,
                 header_template="<span></span>",
                 footer_template=('<div style="width:100%;font-size:8pt;font-family:\'WenQuanYi Zen Hei\',sans-serif;'
                                  'text-align:center;color:#000;">Riffnel_memguard 作品介绍　·　'
                                  '<span class="pageNumber"></span> / <span class="totalPages"></span></div>'),
                 margin={"top": "22mm", "bottom": "22mm", "left": "20mm", "right": "20mm"})


def page_of_headings(pdf: Path, items) -> dict[str, int]:
    """Find the page where a heading stands alone on a line (skips the cover and the table of contents)."""
    reader = PdfReader(str(pdf))
    pages: dict[str, int] = {}
    for n, pg in enumerate(reader.pages, start=1):
        if n < 3:
            continue
        lines = [re.sub(r"\s+", "", ln) for ln in (pg.extract_text() or "").splitlines()]
        for hid, title in items:
            if hid not in pages and re.sub(r"\s+", "", title) in lines:
                pages[hid] = n
    return pages


def main() -> int:
    content = (HERE / "content.html").read_text(encoding="utf-8")
    items = headings(content)
    tmp, final = HERE / "_pass1.pdf", HERE / "Riffnel_memguard_作品介绍.pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, args=["--no-sandbox"])
        page = browser.new_page()
        def doc(pages): return f"<!doctype html><html><head>{HEAD}<style>{CSS}</style></head><body>" \
                               f"{content.replace('{{TOC}}', toc_html(items, pages))}</body></html>"
        render(page, doc({}), tmp)
        pages = page_of_headings(tmp, items)
        missing = [t for h, t in items if h not in pages]
        if missing:
            print("warning: no page found for", missing, file=sys.stderr)
        render(page, doc(pages), final)
        browser.close()
    tmp.unlink()
    n = len(PdfReader(str(final)).pages)
    print(f"wrote {final.name}: {n} pages; headings on pages {pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
