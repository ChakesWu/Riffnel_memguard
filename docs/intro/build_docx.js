// Build the Word version of the introduction from the block model (see extract_docx_model.py).
// Black and white only: thin black table borders, no shading, no coloured text.
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, BorderStyle, AlignmentType,
  HeadingLevel, LevelFormat, PageNumber, Footer, TableOfContents, ImageRun, PageBreak, ShadingType, VerticalAlign,
} = require("docx");

const MODEL = process.argv[2] || "/tmp/intro_docx/model.json";
const OUT = process.argv[3] || "docs/intro/Riffnel_memguard_作品介绍.docx";
const blocks = JSON.parse(fs.readFileSync(MODEL, "utf8"));

const BODY = { ascii: "Times New Roman", hAnsi: "Times New Roman", eastAsia: "SimSun" };
const HEAD = { ascii: "Arial", hAnsi: "Arial", eastAsia: "SimHei" };
const CODE = { ascii: "Consolas", hAnsi: "Consolas", eastAsia: "SimSun" };
const CONTENT_W = 9638; // A4 width 11906 minus 2 x 1134 margins
const BLACK = "000000";
const line = (sz) => ({ style: BorderStyle.SINGLE, size: sz, color: BLACK, space: 1 });
const none = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };

function trimRuns(rs) {
  const out = rs.filter((r) => r.br || r.t !== "");
  if (out.length && out[0].t) out[0] = { ...out[0], t: out[0].t.replace(/^\s+/, "") };
  const last = out.length - 1;
  if (last >= 0 && out[last].t) out[last] = { ...out[last], t: out[last].t.replace(/\s+$/, "") };
  return out;
}
function textRuns(rs, size, forceBold = false) {
  return trimRuns(rs).map((r) => r.br
    ? new TextRun({ break: 1 })
    : new TextRun({ text: r.t, bold: forceBold || r.b, font: r.c ? CODE : BODY, size: r.c ? Math.round(size * 0.92) : size, color: BLACK }));
}
const para = (rs, o = {}) => new Paragraph({
  children: textRuns(rs, o.size || 21, o.bold),
  spacing: { line: o.line || 340, after: o.after ?? 120, before: o.before || 0 },
  alignment: o.align || AlignmentType.JUSTIFIED, border: o.border, indent: o.indent, keepNext: o.keepNext,
});

let olCount = 0;
const numbering = [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
  style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }];

function listBlock(b) {
  let ref = "bullets";
  if (b.type === "ol") {
    ref = `ol${++olCount}`;
    numbering.push({ reference: ref, levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] });
  }
  return b.items.map((rs) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: textRuns(rs, b.small ? 17 : 21),
    spacing: { line: b.small ? 280 : 320, after: b.small ? 40 : 60 }, alignment: AlignmentType.LEFT }));
}

function widths(rows, kv) {
  const n = Math.max(...rows.map((r) => r.length));
  const spec = Array(n).fill(null);
  (rows[0] || []).forEach((c, i) => { if (c.w) spec[i] = c.w; });
  if (kv) spec[0] = 17;
  const given = spec.reduce((a, v) => a + (v || 0), 0);
  const free = spec.filter((v) => v === null).length;
  const each = free ? (100 - given) / free : 0;
  const pct = spec.map((v) => (v === null ? each : v));
  const dxa = pct.map((p) => Math.floor((CONTENT_W * p) / 100));
  dxa[dxa.length - 1] += CONTENT_W - dxa.reduce((a, b) => a + b, 0);
  return dxa;
}

function tableBlock(b, sizeOverride) {
  const small = b.classes.includes("small");
  const kv = b.classes.includes("kv");
  const size = sizeOverride || (small ? 17 : 19);
  const cols = widths(b.rows, kv);
  const border = { top: line(4), left: line(4), bottom: line(4), right: line(4) };
  const rows = b.rows.map((cells) => new TableRow({
    cantSplit: true, tableHeader: cells.every((c) => c.th),
    children: cells.map((c, i) => new TableCell({
      width: { size: cols[i], type: WidthType.DXA }, verticalAlign: VerticalAlign.TOP,
      borders: c.th ? { ...border, bottom: line(10) } : border,
      margins: { top: 50, bottom: 50, left: 100, right: 100 },
      shading: { type: ShadingType.CLEAR, fill: "FFFFFF", color: "auto" },
      children: [new Paragraph({ children: textRuns(c.runs, size, c.th || (kv && i === 0)), alignment: AlignmentType.LEFT,
        spacing: { line: 300, after: 0 } })],
    })),
  }));
  return [new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: cols, rows }),
    new Paragraph({ children: [], spacing: { after: 100 } })];
}

const children = [];
let tocHeading = null;
for (const b of blocks) {
  if (b.type === "cover") {
    children.push(para(b.top, { size: 22, align: AlignmentType.LEFT, before: 1400, after: 1800 }));
    children.push(new Paragraph({ children: [new TextRun({ text: b.title, font: HEAD, size: 60, bold: true, color: BLACK })], spacing: { after: 160 } }));
    children.push(new Paragraph({ children: [new TextRun({ text: b.subtitle, font: HEAD, size: 32, color: BLACK })], spacing: { after: 80 } }));
    children.push(new Paragraph({ children: [new TextRun({ text: b.subtitle_en, font: BODY, size: 22, color: BLACK })], spacing: { after: 1200 } }));
    const t = { ...b.table, classes: ["kv"] };
    children.push(...tableBlock(t, 21));
    children.push(para(b.note, { size: 18, align: AlignmentType.LEFT, before: 200 }));
    children.push(new Paragraph({ children: [new PageBreak()] }));
  } else if (b.type === "toc") {
    children.push(new Paragraph({ children: [new TextRun({ text: "目录", font: HEAD, size: 32, bold: true, color: BLACK })],
      spacing: { after: 240 }, border: { bottom: line(12) } }));
    children.push(new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-1" }));
    children.push(new Paragraph({ children: [new PageBreak()] }));
  } else if (b.type === "h1") {
    children.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: !!b.newpage, children: [new TextRun({ text: b.text, font: HEAD, size: 32, bold: true, color: BLACK })] }));
  } else if (b.type === "h2") {
    children.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun({ text: b.text, font: HEAD, size: 24, bold: true, color: BLACK })] }));
  } else if (b.type === "p") {
    if (b.kind === "lead") {
      const bd = { top: line(6), left: line(6), bottom: line(6), right: line(6) };
      children.push(new Table({ width: { size: CONTENT_W, type: WidthType.DXA }, columnWidths: [CONTENT_W], rows: [new TableRow({ cantSplit: true, children: [
        new TableCell({ width: { size: CONTENT_W, type: WidthType.DXA }, borders: bd, margins: { top: 80, bottom: 80, left: 140, right: 140 },
          shading: { type: ShadingType.CLEAR, fill: "FFFFFF", color: "auto" }, children: [para(b.runs, { after: 0 })] })] })] }));
      children.push(new Paragraph({ children: [], spacing: { after: 80 } }));
    } else if (b.kind === "note") children.push(para(b.runs, { size: 19 }));
    else children.push(para(b.runs));
  } else if (b.type === "ul" || b.type === "ol") children.push(...listBlock(b));
  else if (b.type === "table") children.push(...tableBlock(b));
  else if (b.type === "fig") {
    const w = 600, h = Math.round((b.h * w) / b.w);
    children.push(new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 120, after: 40 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(b.path), transformation: { width: w, height: h },
        altText: { title: b.caption, description: b.caption, name: b.caption } })] }));
    children.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 160 }, children: [new TextRun({ text: b.caption, font: BODY, size: 19, color: BLACK })] }));
  }
}

const footer = new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [
  new TextRun({ text: "Riffnel_memguard 作品介绍　·　", font: BODY, size: 16, color: BLACK }),
  new TextRun({ children: [PageNumber.CURRENT], font: BODY, size: 16, color: BLACK }),
  new TextRun({ text: " / ", font: BODY, size: 16, color: BLACK }),
  new TextRun({ children: [PageNumber.TOTAL_PAGES], font: BODY, size: 16, color: BLACK }),
] })] });

const doc = new Document({
  creator: "Riffnel_memguard", title: "Riffnel_memguard 作品介绍（草稿）",
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: BODY, size: 21, color: BLACK } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: HEAD, size: 32, bold: true, color: BLACK },
        paragraph: { spacing: { before: 420, after: 160 }, outlineLevel: 0, keepNext: true, border: { bottom: line(12) } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: HEAD, size: 24, bold: true, color: BLACK },
        paragraph: { spacing: { before: 260, after: 100 }, outlineLevel: 1, keepNext: true } },
    ],
  },
  numbering: { config: numbering },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1247, bottom: 1247, left: 1134, right: 1134 } }, titlePage: true },
    footers: { default: footer, first: new Footer({ children: [new Paragraph({ children: [] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then((buf) => { fs.writeFileSync(OUT, buf); console.log("wrote", OUT, buf.length, "bytes"); });
