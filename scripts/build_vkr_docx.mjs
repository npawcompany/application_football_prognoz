#!/usr/bin/env node
/**
 * Assemble docs/vkr/vkr.docx from manuscript markdown (TSU 2024).
 * Usage: node scripts/build_vkr_docx.mjs
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  AlignmentType, BorderStyle, Document, Footer, HeadingLevel, ImageRun,
  Packer, PageNumber, Paragraph, PositionalTab, PositionalTabAlignment,
  PositionalTabLeader, PositionalTabRelativeTo, ShadingType, Table, TableCell,
  TableRow, TextRun, VerticalAlign, WidthType, convertMillimetersToTwip,
} from "docx";
import { injectOfficeParts } from "./vkr_office.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const MS = path.join(ROOT, "docs/vkr/manuscript");
const OUT = path.join(ROOT, "docs/vkr/vkr.docx");

const PAGE_W = 11906, PAGE_H = 16838;
const MARGIN = {
  top: convertMillimetersToTwip(20),
  bottom: convertMillimetersToTwip(20),
  left: convertMillimetersToTwip(30),
  right: convertMillimetersToTwip(15),
};
const CONTENT_W = PAGE_W - MARGIN.left - MARGIN.right;
const INDENT = convertMillimetersToTwip(12.5);
const FONT = "Times New Roman";
const SIZE_BODY = 28, SIZE_CAPTION = 24, SIZE_NOTE = 20;
const LINE_15 = 360, LINE_10 = 240;
const EMPTY = "–";

const NO_BORDER = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const NO_BORDERS = { top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER };
const THIN = { style: BorderStyle.SINGLE, size: 8, color: "000000" };
const THIN_BORDERS = { top: THIN, bottom: THIN, left: THIN, right: THIN };

const FIGURE_DEFS = [
  { key: "ожидание Эло от разницы рейтингов", chart: "elo", caption: "Ожидание Эло от разницы рейтингов" },
  { key: "столбцы вероятностей 1 / X / 2", chart: "bars", caption: "Вероятности исходов 1 / X / 2" },
  { key: "слои приложения", file: "figures/drawio/layers.png", caption: "Слоистая архитектура приложения" },
  { key: "контекст системы", file: "figures/drawio/context.png", caption: "Контекстная диаграмма системы" },
  { key: "последовательность прогноза", file: "figures/drawio/forecast-sequence.png", caption: "Последовательность расчёта прогноза" },
  { key: "таблицы кэша SQLite", file: "figures/drawio/sqlite-cache.png", caption: "Таблицы локального кэша SQLite" },
  { key: "переходы экранов", file: "figures/drawio/screens-nav.png", caption: "Переходы экранов приложения" },
  { key: "экран лиг", file: "figures/screens/leagues.png", caption: "Экран выбора лиг" },
  { key: "экран календаря", file: "figures/screens/fixtures.png", caption: "Экран календаря матчей" },
  { key: "экран прогноза", file: "figures/screens/forecast.png", caption: "Экран прогноза матча" },
];

const figureIndex = new Map();
const missingImages = [];
const formulas = [];
let nextFigure = 1;

function pngSize(buf) {
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

function loadImage(relPath) {
  const abs = path.join(MS, relPath);
  if (!fs.existsSync(abs)) { missingImages.push(relPath); return null; }
  const data = fs.readFileSync(abs);
  const { width, height } = pngSize(data);
  const maxW = 430;
  const scale = Math.min(1, maxW / width);
  return { data, width: Math.round(width * scale), height: Math.round(height * scale) };
}

function ensureFigure(key) {
  if (figureIndex.has(key)) return figureIndex.get(key);
  const def = FIGURE_DEFS.find((d) => d.key === key);
  if (!def) return null;
  const entry = { ...def, num: nextFigure++, image: def.file ? loadImage(def.file) : null };
  figureIndex.set(key, entry);
  return entry;
}

function emptyLine() {
  return new Paragraph({ spacing: { after: 0, line: LINE_15 }, children: [] });
}

function run(text, opts = {}) {
  return new TextRun({
    text, font: FONT, size: opts.size ?? SIZE_BODY,
    bold: !!opts.bold, italics: !!opts.italics, color: "000000",
  });
}

function latexToPlain(s) {
  return s
    .replace(/\\mathrm\{([^}]+)\}/g, "$1")
    .replace(/\\mathrm/g, "")
    .replace(/\\operatorname\{([^}]+)\}/g, "$1")
    .replace(/\\text\{([^}]+)\}/g, "$1")
    .replace(/\\bigl|\\bigr|\\big|\\left|\\right/g, "")
    .replace(/\\cdot/g, "·").replace(/\\times/g, "×").replace(/\\approx/g, "≈")
    .replace(/\\leq/g, "≤").replace(/\\geq/g, "≥").replace(/\\neq/g, "≠")
    .replace(/\\infty/g, "∞").replace(/\\sum/g, "∑").replace(/\\ln/g, "ln")
    .replace(/\\tanh/g, "tanh").replace(/\\max/g, "max").replace(/\\min/g, "min")
    .replace(/\\clip/g, "clip").replace(/\\tag\{[^}]+\}/g, "")
    .replace(/\\qquad/g, "    ").replace(/\\quad/g, "  ")
    .replace(/\\,/g, " ").replace(/\\;/g, " ").replace(/\\!/g, "")
    .replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, "($1)/($2)")
    .replace(/\^\{([^}]+)\}/g, "^($1)").replace(/_\{([^}]+)\}/g, "_($1)")
    .replace(/\\/g, "").replace(/[{}]/g, "").replace(/\s+/g, " ").trim();
}

function inlineRuns(text, size = SIZE_BODY) {
  const runs = [];
  const re = /(\$[^$]+\$|`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) runs.push(run(text.slice(last, m.index), { size }));
    const token = m[0];
    if (token.startsWith("$")) runs.push(run(latexToPlain(token.slice(1, -1)), { size, italics: true }));
    else if (token.startsWith("`")) runs.push(run(token.slice(1, -1), { size }));
    else runs.push(run(token.slice(2, -2), { size, bold: true }));
    last = m.index + token.length;
  }
  if (last < text.length) runs.push(run(text.slice(last), { size }));
  if (!runs.length) runs.push(run("", { size }));
  return runs;
}

function bodyPara(text, opts = {}) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED,
    indent: { firstLine: opts.noIndent ? 0 : INDENT },
    spacing: { after: 0, line: LINE_15, before: opts.before ?? 0 },
    children: inlineRuns(text, opts.size ?? SIZE_BODY),
  });
}

function structuralHeading(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1, pageBreakBefore: true, keepNext: true, keepLines: true,
    alignment: AlignmentType.CENTER, indent: { firstLine: 0 },
    spacing: { after: 200, line: LINE_15, before: 0 },
    children: [run(text, { bold: true, size: SIZE_BODY })],
  });
}

function chapterHeading(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1, pageBreakBefore: true, keepNext: true, keepLines: true,
    alignment: AlignmentType.JUSTIFIED, indent: { firstLine: INDENT },
    spacing: { after: 200, line: LINE_15, before: 0 },
    children: [run(text, { bold: true, size: SIZE_BODY })],
  });
}

function sectionHeading(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2, keepNext: true, keepLines: true,
    alignment: AlignmentType.JUSTIFIED, indent: { firstLine: INDENT },
    spacing: { before: 240, after: 200, line: LINE_15 },
    children: [run(text, { bold: true, size: SIZE_BODY })],
  });
}

function subsectionHeading(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED, indent: { firstLine: INDENT },
    spacing: { before: LINE_15, after: 0, line: LINE_15 },
    children: [run(text, { bold: true, size: SIZE_BODY })],
  });
}

function listItem(text) {
  const content = text.replace(/^[–\-]\s*/, "");
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED, indent: { firstLine: INDENT },
    spacing: { after: 0, line: LINE_15 },
    children: [run(`– ${content}`, { size: SIZE_BODY })],
  });
}

function captionTable(text) {
  return new Paragraph({
    alignment: AlignmentType.JUSTIFIED, indent: { firstLine: 0 },
    spacing: { before: LINE_15, after: 120, line: LINE_10 },
    children: [run(text, { size: SIZE_CAPTION })],
  });
}

function captionFigure(text) {
  return new Paragraph({
    alignment: AlignmentType.CENTER, indent: { firstLine: 0 },
    spacing: { before: 120, after: LINE_15, line: LINE_10 },
    children: [run(text, { size: SIZE_CAPTION })],
  });
}

function makeTable(headers, rows) {
  const cols = headers.length;
  const colW = Math.floor(CONTENT_W / cols);
  const widths = Array(cols).fill(colW);
  widths[cols - 1] = CONTENT_W - colW * (cols - 1);
  const mkCell = (text, header, i) => new TableCell({
    borders: THIN_BORDERS,
    width: { size: widths[i], type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: "FFFFFF" },
    margins: { top: 40, bottom: 40, left: 60, right: 60 },
    verticalAlign: VerticalAlign.TOP,
    children: [new Paragraph({
      alignment: header ? AlignmentType.CENTER : AlignmentType.LEFT,
      spacing: { after: 0, line: LINE_10 },
      children: [run(
        text === "" || text === "-" || text === "—" ? EMPTY : String(text).trim(),
        { size: SIZE_CAPTION, bold: header }
      )],
    })],
  });
  return new Table({
    width: { size: CONTENT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ children: headers.map((h, i) => mkCell(h, true, i)) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => mkCell(c, false, i)) })),
    ],
  });
}

function formulaBlock(raw) {
  const tagMatch = raw.match(/\\tag\{([^}]+)\}/);
  const num = tagMatch ? tagMatch[1].trim() : null;
  const latex = raw.split("\n").map((l) => l.trim()).filter(Boolean).join(" ");
  const idx = formulas.length;
  formulas.push({ latex, num });
  return [new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 0, line: LINE_10 },
    children: [run(`[[F${idx}]]`)],
  })];
}

function figureBlocks(entry) {
  const out = [];
  if (entry.chart) {
    out.push(new Paragraph({
      alignment: AlignmentType.CENTER,
      spacing: { before: 200, after: 0, line: LINE_10 },
      children: [run(`[[C${entry.chart}]]`)],
    }));
    out.push(captionFigure(`Рисунок ${entry.num} – ${entry.caption}`));
    return out;
  }
  if (entry.image) {
    out.push(new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: 0, line: LINE_10 },
      children: [new ImageRun({
        type: "png", data: entry.image.data,
        transformation: { width: entry.image.width, height: entry.image.height },
        altText: { title: `Рисунок ${entry.num}`, description: entry.caption, name: `fig${entry.num}` },
      })],
    }));
  } else {
    out.push(bodyPara(`[Рисунок ${entry.num}: файл ${entry.file} отсутствует]`, { noIndent: true }));
  }
  out.push(captionFigure(`Рисунок ${entry.num} – ${entry.caption}`));
  return out;
}

function processParagraphText(text) {
  const keys = [];
  const t = text.replace(/\(рисунок:\s*([^)]+)\)/gi, (full, inner) => {
    const parts = inner.split(/;\s*(?=рисунок:)/i).map((p) => p.replace(/^рисунок:\s*/i, "").trim());
    const nums = [];
    for (const k of parts) {
      const entry = ensureFigure(k);
      if (entry) { keys.push(entry); nums.push(entry.num); }
    }
    if (!nums.length) return full;
    return nums.length === 1 ? `(рисунок ${nums[0]})` : `(рисунки ${nums.join(", ")})`;
  });
  return { text: t, figures: keys };
}

function parseMarkdownTable(lines) {
  const split = (line) => line.replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
  return { headers: split(lines[0]), rows: lines.slice(2).map(split) };
}

function parseMdFile(rel) {
  let md = fs.readFileSync(path.join(MS, rel), "utf8").replace(/^#\s+[^\n]+\n+/, "");
  const lines = md.split(/\r?\n/);
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) { i++; continue; }
    if (line.trim().startsWith("```")) {
      i++; const code = [];
      while (i < lines.length && !lines[i].trim().startsWith("```")) { code.push(lines[i]); i++; }
      i++; blocks.push({ type: "code", lines: code }); continue;
    }
    if (line.trim() === "$$") {
      i++; const math = [];
      while (i < lines.length && lines[i].trim() !== "$$") { math.push(lines[i]); i++; }
      i++; blocks.push({ type: "formula", raw: math.join("\n") }); continue;
    }
    if (/^Таблица\s/.test(line.trim())) { blocks.push({ type: "tableCaption", text: line.trim() }); i++; continue; }
    if (line.trim().startsWith("|")) {
      const tbl = [];
      while (i < lines.length && lines[i].trim().startsWith("|")) { tbl.push(lines[i]); i++; }
      if (tbl.length >= 2) { const { headers, rows } = parseMarkdownTable(tbl); blocks.push({ type: "table", headers, rows }); }
      continue;
    }
    if (line.startsWith("### ")) { blocks.push({ type: "h3", text: line.slice(4).trim() }); i++; continue; }
    if (line.startsWith("## ")) { blocks.push({ type: "h2", text: line.slice(3).trim() }); i++; continue; }
    if (line.startsWith("# ")) { blocks.push({ type: "h1", text: line.slice(2).trim() }); i++; continue; }
    if (/^[–\-]\s+/.test(line.trim())) {
      const items = [];
      while (i < lines.length && /^[–\-]\s+/.test(lines[i].trim())) { items.push(lines[i].trim()); i++; }
      blocks.push({ type: "ul", items }); continue;
    }
    if (/^\d+[.)]\s+/.test(line.trim())) {
      const items = [];
      while (i < lines.length && /^\d+[.)]\s+/.test(lines[i].trim())) { items.push(lines[i].trim()); i++; }
      blocks.push({ type: "ol", items }); continue;
    }
    if (/^Примечание\s*[–-]/.test(line.trim())) { blocks.push({ type: "note", text: line.trim() }); i++; continue; }
    let para = line; i++;
    while (i < lines.length && lines[i].trim() && !lines[i].startsWith("#") && !lines[i].trim().startsWith("```")
      && lines[i].trim() !== "$$" && !lines[i].trim().startsWith("|") && !/^[–\-]\s+/.test(lines[i].trim())
      && !/^\d+[.)]\s+/.test(lines[i].trim()) && !/^Таблица\s/.test(lines[i].trim())
      && !/^Примечание\s*[–-]/.test(lines[i].trim())) {
      para += " " + lines[i].trim(); i++;
    }
    blocks.push({ type: "p", text: para.trim() });
  }
  return blocks;
}

function blocksToParagraphs(blocks) {
  const out = [];
  for (const b of blocks) {
    if (b.type === "h1") { out.push(chapterHeading(b.text)); continue; }
    if (b.type === "h2") { out.push(sectionHeading(b.text)); continue; }
    if (b.type === "h3") { out.push(subsectionHeading(b.text)); continue; }
    if (b.type === "p") {
      const { text, figures } = processParagraphText(b.text);
      out.push(bodyPara(text));
      for (const fig of figures) out.push(...figureBlocks(fig));
      continue;
    }
    if (b.type === "ul") { for (const it of b.items) out.push(listItem(it)); continue; }
    if (b.type === "ol") { for (const it of b.items) out.push(bodyPara(it)); continue; }
    if (b.type === "formula") { out.push(...formulaBlock(b.raw)); continue; }
    if (b.type === "tableCaption") { out.push(emptyLine()); out.push(captionTable(b.text)); continue; }
    if (b.type === "table") { out.push(makeTable(b.headers, b.rows)); out.push(emptyLine()); continue; }
    if (b.type === "note") {
      out.push(new Paragraph({
        alignment: AlignmentType.JUSTIFIED, indent: { firstLine: INDENT },
        spacing: { after: 0, line: LINE_10 },
        children: [run(b.text, { size: SIZE_NOTE })],
      }));
      continue;
    }
    if (b.type === "code") {
      out.push(emptyLine());
      for (const cl of b.lines) {
        out.push(new Paragraph({
          alignment: AlignmentType.LEFT, indent: { firstLine: 0, left: INDENT },
          spacing: { after: 0, line: LINE_10 },
          children: [run(cl || " ", { size: SIZE_CAPTION })],
        }));
      }
      out.push(emptyLine());
    }
  }
  return out;
}

function titlePage() {
  const center = (text, opts = {}) => new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: opts.after ?? 0, line: LINE_15, before: opts.before ?? 0 },
    children: [run(text, { size: opts.size ?? SIZE_BODY, bold: !!opts.bold })],
  });
  const left = (text) => new Paragraph({
    alignment: AlignmentType.LEFT, spacing: { after: 0, line: LINE_15 },
    children: [run(text, { size: SIZE_BODY })],
  });
  return [
    center("МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ", { before: 200 }),
    center("РОССИЙСКОЙ ФЕДЕРАЦИИ"),
    center("Тольяттинский государственный университет", { after: 400 }),
    center("Кафедра: ________________________________"),
    emptyLine(), emptyLine(),
    center("ВЫПУСКНАЯ КВАЛИФИКАЦИОННАЯ РАБОТА", { bold: true, after: 200 }),
    center("(бакалаврская работа)", { after: 400 }),
    center("на тему:", { after: 200 }),
    center("«Разработка настольного приложения статистического", { bold: true }),
    center("прогнозирования исходов футбольных матчей»", { bold: true, after: 600 }),
    emptyLine(), emptyLine(),
    left("Студент: _______________________________ / ____________________ /"),
    left("Группа: _______________________________"),
    emptyLine(),
    left("Руководитель: _________________________ / ____________________ /"),
    emptyLine(), emptyLine(),
    center("Тольятти 2026"),
  ];
}

function tocEntry(title, page, level = 0) {
  const indent = level === 0 ? 0 : convertMillimetersToTwip(5);
  return new Paragraph({
    alignment: AlignmentType.LEFT, indent: { left: indent, firstLine: 0 },
    spacing: { after: 0, line: LINE_15 },
    children: [
      run(title, { size: SIZE_BODY }),
      new TextRun({
        children: [new PositionalTab({
          alignment: PositionalTabAlignment.RIGHT,
          relativeTo: PositionalTabRelativeTo.MARGIN,
          leader: PositionalTabLeader.DOT,
        })],
        font: FONT, size: SIZE_BODY,
      }),
      run(String(page), { size: SIZE_BODY }),
    ],
  });
}

function estimatePageMap() {
  return {
    annot: 2, intro: 4, ch1: 7, s11: 7, s12: 15, s13: 16,
    ch2: 18, s21: 18, s22: 22, s23: 28, ch3: 30, s31: 30, s32: 33, s33: 35,
    concl: 42, bib: 44, appA: 46, appB: 48, appV: 50, appG: 52, appD: 54,
  };
}

function loadPageMap() {
  const p = path.join(ROOT, "docs/vkr/.toc-pages.json");
  if (fs.existsSync(p)) {
    try { return { ...estimatePageMap(), ...JSON.parse(fs.readFileSync(p, "utf8")) }; } catch { /* */ }
  }
  return estimatePageMap();
}

function buildToc(pageMap) {
  const entries = [
    ["Аннотация", "annot", 0], ["Введение", "intro", 0],
    ["1 Предметная область и постановка задачи", "ch1", 0],
    ["1.1 Особенности прогноза футбольного матча и методы, принятые в работе", "s11", 1],
    ["1.2 Существующие решения спортивной аналитики", "s12", 1],
    ["1.3 Требования к программному обеспечению", "s13", 1],
    ["2 Проектирование", "ch2", 0],
    ["2.1 Технологии и архитектура", "s21", 1],
    ["2.2 Информационная модель и модуль прогноза", "s22", 1],
    ["2.3 Пользовательский интерфейс", "s23", 1],
    ["3 Реализация и оценка", "ch3", 0],
    ["3.1 Загрузка данных и прогноз", "s31", 1],
    ["3.2 Графический интерфейс и пояснение", "s32", 1],
    ["3.3 Тестирование и качество прогноза", "s33", 1],
    ["Заключение", "concl", 0],
    ["Список используемой литературы и используемых источников", "bib", 0],
    ["Приложение А Техническое задание на разработку настольного приложения статистического прогнозирования исходов футбольных матчей", "appA", 0],
    ["Приложение Б Описание локального кэша SQLite", "appB", 0],
    ["Приложение В Руководство пользователя", "appV", 0],
    ["Приложение Г Листинги ключевых фрагментов", "appG", 0],
    ["Приложение Д Примеры прогнозов", "appD", 0],
  ];
  const out = [structuralHeading("Оглавление")];
  for (const [title, key, level] of entries) out.push(tocEntry(title, pageMap[key] ?? "…", level));
  return out;
}

function appendixHeader(letter, title) {
  return [
    new Paragraph({
      pageBreakBefore: true, alignment: AlignmentType.CENTER,
      spacing: { after: 0, line: LINE_15 },
      children: [run(`Приложение ${letter}`, { size: SIZE_BODY })],
    }),
    new Paragraph({
      alignment: AlignmentType.CENTER, spacing: { after: LINE_15, line: LINE_15 },
      children: [run(title, { size: SIZE_BODY, bold: true })],
    }),
  ];
}

function pageFooter() {
  return new Footer({
    children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: SIZE_CAPTION })],
    })],
  });
}

function assemble() {
  const pageMap = loadPageMap();
  const children = [];
  children.push(structuralHeading("Аннотация"));
  children.push(...blocksToParagraphs(parseMdFile("00-annotaciya.md")));
  children.push(...buildToc(pageMap));
  children.push(structuralHeading("Введение"));
  children.push(...blocksToParagraphs(parseMdFile("01-vvedenie.md")));
  for (const [file] of [["02-glava-1.md"], ["03-glava-2.md"], ["04-glava-3.md"]]) {
    const raw = fs.readFileSync(path.join(MS, file), "utf8");
    const title = raw.match(/^#\s+(.+)$/m)[1].trim();
    children.push(chapterHeading(title));
    children.push(...blocksToParagraphs(parseMdFile(file)));
  }
  children.push(structuralHeading("Заключение"));
  children.push(...blocksToParagraphs(parseMdFile("05-zaklyuchenie.md")));
  children.push(structuralHeading("Список используемой литературы и используемых источников"));
  children.push(...blocksToParagraphs(parseMdFile("06-literatura.md")));
  const apps = [
    ["А", "Техническое задание на разработку настольного приложения статистического прогнозирования исходов футбольных матчей", "pril-a-tz.md"],
    ["Б", "Описание локального кэша SQLite", "pril-b-bd.md"],
    ["В", "Руководство пользователя", "pril-v-rukovodstvo.md"],
    ["Г", "Листинги ключевых фрагментов", "pril-g-listingi.md"],
    ["Д", "Примеры прогнозов", "pril-d-prognozy.md"],
  ];
  for (const [letter, title, file] of apps) {
    children.push(...appendixHeader(letter, title));
    let blocks = parseMdFile(file);
    while (blocks.length && (blocks[0].type === "h1" || blocks[0].type === "h2")) blocks = blocks.slice(1);
    children.push(...blocksToParagraphs(blocks));
  }
  const pageProps = { size: { width: PAGE_W, height: PAGE_H }, margin: MARGIN };
  return new Document({
    styles: {
      default: {
        document: {
          run: { font: FONT, size: SIZE_BODY, color: "000000" },
          paragraph: { alignment: AlignmentType.JUSTIFIED, spacing: { line: LINE_15, after: 0 } },
        },
      },
      paragraphStyles: [
        { id: "Normal", name: "Normal",
          run: { font: FONT, size: SIZE_BODY },
          paragraph: { alignment: AlignmentType.JUSTIFIED, indent: { firstLine: INDENT }, spacing: { line: LINE_15, after: 0 } } },
        { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: FONT, size: SIZE_BODY, bold: true, color: "000000" },
          paragraph: { spacing: { before: 0, after: LINE_15, line: LINE_15 }, outlineLevel: 0 } },
        { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
          run: { font: FONT, size: SIZE_BODY, bold: true, color: "000000" },
          paragraph: { spacing: { before: LINE_15, after: LINE_15, line: LINE_15 }, indent: { firstLine: INDENT }, outlineLevel: 1 } },
      ],
    },
    sections: [
      { properties: { page: { ...pageProps, pageNumbers: { start: 1 } } }, children: titlePage() },
      { properties: { page: { ...pageProps, pageNumbers: { start: 2 } } },
        footers: { default: pageFooter() }, children },
    ],
  });
}

async function main() {
  const doc = assemble();
  const raw = await Packer.toBuffer(doc);
  const buf = await injectOfficeParts(raw, formulas);
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, buf);
  console.log(`Wrote ${OUT} (${buf.length} bytes)`);
  console.log(`Figures: ${figureIndex.size}/${FIGURE_DEFS.length}`);
  for (const [, v] of figureIndex) console.log(`  Fig ${v.num}: ${v.file} ${v.image ? "OK" : "MISSING"}`);
  if (missingImages.length) console.log("Missing:", missingImages.join(", "));
  fs.writeFileSync(path.join(ROOT, "docs/vkr/.build-report.json"), JSON.stringify({
    out: OUT,
    figures: [...figureIndex.values()].map((v) => ({ num: v.num, key: v.key, file: v.file, ok: !!v.image })),
    missingImages,
  }, null, 2));
}

main().catch((e) => { console.error(e); process.exit(1); });
