"""Build the Word version of the introduction.

Steps: parse content.html -> block model + figure PNGs -> docx (node + docx-js) -> lay out once with LibreOffice to
find each chapter's page -> fill the table of contents field with those entries (Word refreshes the field when asked).
Needs: node with the `docx` package, playwright + Chromium, bs4, pypdf, and LibreOffice (`soffice`) for page numbers.
"""
from __future__ import annotations

import glob
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from pypdf import PdfReader

HERE = Path(__file__).parent
DOCX = HERE / "Riffnel_memguard_作品介绍.docx"
MODEL = Path("/tmp/intro_docx/model.json")
CONTENT_W = 9638


def soffice_cmd() -> list[str] | None:
    if shutil.which("soffice"):
        return ["soffice"]
    hits = glob.glob("/root/.claude/skills/synced/*/docx/scripts/office/soffice.py")
    return [sys.executable, hits[0]] if hits else None


def chapter_pages(docx: Path, titles: list[str]) -> dict[str, int]:
    cmd = soffice_cmd()
    if not cmd:
        return {}
    with tempfile.TemporaryDirectory() as d:
        subprocess.run([*cmd, "--headless", "--convert-to", "pdf", "--outdir", d, str(docx)], check=True,
                       capture_output=True)
        reader = PdfReader(str(next(Path(d).glob("*.pdf"))))
        pages: dict[str, int] = {}
        for n, pg in enumerate(reader.pages, start=1):
            if n < 3:
                continue
            lines = [re.sub(r"\s+", "", ln) for ln in (pg.extract_text() or "").splitlines()]
            for t in titles:
                if t not in pages and re.sub(r"\s+", "", t) in lines:
                    pages[t] = n
        return pages


def entry(title: str, page: str | None) -> str:
    esc = title.replace("&", "&amp;").replace("<", "&lt;")
    tab = (f'<w:r><w:tab/></w:r><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:eastAsia="SimSun"/><w:sz w:val="22"/></w:rPr>'
           f'<w:t>{page}</w:t></w:r>') if page else ""
    return ('<w:p><w:pPr><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="%d"/></w:tabs><w:spacing w:after="120"/></w:pPr>'
            '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:eastAsia="SimSun"/><w:sz w:val="22"/></w:rPr><w:t xml:space="preserve">%s</w:t></w:r>%s</w:p>'
            % (CONTENT_W, esc, tab))


def inject_toc(docx: Path, titles: list[str], pages: dict[str, int]) -> None:
    tmp = docx.with_suffix(".tmp")
    with zipfile.ZipFile(docx) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                xml = data.decode("utf-8")
                marker = '<w:fldChar w:fldCharType="separate"/></w:r></w:p>'
                assert xml.count(marker) == 1, "unexpected TOC structure"
                cached = "".join(entry(t, str(pages[t]) if t in pages else None) for t in titles)
                xml = xml.replace(marker, marker + cached)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    tmp.replace(docx)


def main() -> int:
    subprocess.run([sys.executable, str(HERE / "extract_docx_model.py")], check=True)
    subprocess.run(["node", str(HERE / "build_docx.js"), str(MODEL), str(DOCX)], check=True)
    blocks = json.loads(MODEL.read_text(encoding="utf-8"))
    titles = [b["text"] for b in blocks if b["type"] == "h1"]
    pages = chapter_pages(DOCX, titles)
    missing = [t for t in titles if t not in pages]
    if missing:
        print("warning: no page number for", missing, file=sys.stderr)
    inject_toc(DOCX, titles, pages)
    print(f"wrote {DOCX.name}; chapter pages (LibreOffice layout, Word may differ slightly): {pages}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
