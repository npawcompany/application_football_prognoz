/**
 * OMML formulas and native Word charts for the thesis docx.
 */
import JSZip from "jszip";

const M_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math";
const C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart";

function esc(s) {
  return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function r(text, plain = false) {
  const sty = plain ? "<m:rPr><m:sty m:val=\"p\"/></m:rPr>" : "";
  return `<m:r>${sty}<m:t xml:space="preserve">${esc(text)}</m:t></m:r>`;
}

function readGroup(s, i) {
  if (s[i] !== "{") return null;
  let depth = 0;
  for (let j = i; j < s.length; j++) {
    if (s[j] === "{") depth++;
    else if (s[j] === "}") {
      depth--;
      if (depth === 0) return { inner: s.slice(i + 1, j), next: j + 1 };
    }
  }
  return null;
}

function parseSeq(s) {
  const parts = [];
  let i = 0;
  const pushText = (t) => { if (t) parts.push({ t: "text", v: t }); };
  while (i < s.length) {
    if (s[i] === " " || s[i] === "\n") { i++; continue; }
    if (s.startsWith("\\frac", i)) {
      i += 5;
      const num = readGroup(s, i);
      const den = num && readGroup(s, num.next);
      if (!num || !den) break;
      parts.push({ t: "frac", num: parseSeq(num.inner), den: parseSeq(den.inner) });
      i = den.next;
      continue;
    }
    const cmd = s.slice(i).match(/^\\(mathrm|operatorname|text|tanh|max|min|clip|ln|cdot|times|quad|qquad|left|right|bigl|bigr|Bigl|Bigr|big|tag|approx|leftarrow)/);
    if (cmd) {
      i += cmd[0].length;
      if (cmd[1] === "mathrm" || cmd[1] === "operatorname" || cmd[1] === "text") {
        const g = readGroup(s, i);
        if (g) { parts.push({ t: "plain", v: g.inner }); i = g.next; }
      } else if (cmd[1] === "cdot") parts.push({ t: "text", v: "·" });
      else if (cmd[1] === "times") parts.push({ t: "text", v: "×" });
      else if (cmd[1] === "quad" || cmd[1] === "qquad") parts.push({ t: "text", v: cmd[1] === "qquad" ? "    " : "  " });
      else if (cmd[1] === "approx") parts.push({ t: "text", v: "≈" });
      else if (cmd[1] === "leftarrow") parts.push({ t: "text", v: "←" });
      else if (cmd[1] === "tanh") parts.push({ t: "plain", v: "tanh" });
      else if (cmd[1] === "max" || cmd[1] === "min" || cmd[1] === "ln" || cmd[1] === "clip") parts.push({ t: "plain", v: cmd[1] });
      else if (cmd[1] === "tag") {
        const g = readGroup(s, i);
        if (g) i = g.next;
      }
      continue;
    }
    if (s[i] === "\\") { i++; continue; }
    if (s[i] === "_" || s[i] === "^") {
      const kind = s[i] === "_" ? "sub" : "sup";
      i++;
      let inner;
      if (s[i] === "{") {
        const g = readGroup(s, i);
        inner = g ? parseSeq(g.inner) : [];
        i = g ? g.next : i + 1;
      } else {
        inner = parseSeq(s[i]);
        i++;
      }
      const base = parts.pop() || { t: "text", v: "" };
      const prev = parts[parts.length - 1];
      if (prev && prev.t === "script" && prev.base === base) {
        prev[kind] = inner;
      } else if (base.t === "script") {
        base[kind] = inner;
        parts.push(base);
      } else {
        parts.push({ t: "script", base, [kind]: inner });
      }
      continue;
    }
    if (s[i] === "{" ) {
      const g = readGroup(s, i);
      if (!g) break;
      parts.push(...parseSeq(g.inner));
      i = g.next;
      continue;
    }
    if (s[i] === "}" || s[i] === "&") { i++; continue; }
    let j = i + 1;
    while (j < s.length && !" \\_^{}".includes(s[j]) && s[j] !== "\n") j++;
    pushText(s.slice(i, j));
    i = j;
  }
  return parts;
}

function emit(parts) {
  return parts.map(emitOne).join("");
}

function emitOne(node) {
  if (!node) return "";
  if (node.t === "text") return r(node.v, false);
  if (node.t === "plain") return r(node.v, true);
  if (node.t === "frac") {
    return `<m:f><m:num>${emit(node.num)}</m:num><m:den>${emit(node.den)}</m:den></m:f>`;
  }
  if (node.t === "script") {
    const base = emitOne(node.base);
    if (node.sub && node.sup) {
      return `<m:sSubSup><m:e>${base}</m:e><m:sub>${emit(node.sub)}</m:sub><m:sup>${emit(node.sup)}</m:sup></m:sSubSup>`;
    }
    if (node.sub) return `<m:sSub><m:e>${base}</m:e><m:sub>${emit(node.sub)}</m:sub></m:sSub>`;
    if (node.sup) return `<m:sSup><m:e>${base}</m:e><m:sup>${emit(node.sup)}</m:sup></m:sSup>`;
    return base;
  }
  return "";
}

export function latexToOmml(src) {
  const cleaned = src.replace(/\\tag\{[^}]*\}/g, "");
  return `<m:oMath>${emit(parseSeq(cleaned))}</m:oMath>`;
}

function numPts(values) {
  return values.map((v, i) => `<c:pt idx="${i}"><c:v>${v}</c:v></c:pt>`).join("");
}
function strPts(values) {
  return values.map((v, i) => `<c:pt idx="${i}"><c:v>${esc(v)}</c:v></c:pt>`).join("");
}

function axis(id, other, pos, percent) {
  const num = percent
    ? `<c:numFmt formatCode="0%" sourceLinked="0"/>`
    : `<c:numFmt formatCode="General" sourceLinked="0"/>`;
  const tag = pos === "b" ? "c:catAx" : "c:valAx";
  return `<${tag}><c:axId val="${id}"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:delete val="0"/><c:axPos val="${pos}"/>${pos === "l" ? num : ""}<c:majorTickMark val="out"/><c:minorTickMark val="none"/><c:tickLblPos val="nextTo"/><c:crossAx val="${other}"/><c:crosses val="autoZero"/></${tag}>`;
}

export function chartXml({ kind, title, cats, values, yTitle }) {
  const n = cats.length;
  const ser = `<c:ser><c:idx val="0"/><c:order val="0"/><c:tx><c:v>${esc(yTitle)}</c:v></c:tx><c:spPr><a:solidFill><a:srgbClr val="FFFFFF"/></a:solidFill><a:ln w="12700"><a:solidFill><a:srgbClr val="000000"/></a:solidFill></a:ln></c:spPr><c:cat><c:strLit><c:ptCount val="${n}"/>${strPts(cats)}</c:strLit></c:cat><c:val><c:numLit><c:formatCode>${kind === "bar" ? "0%" : "0.00"}</c:formatCode><c:ptCount val="${n}"/>${numPts(values)}</c:numLit></c:val></c:ser>`;
  const plot = kind === "bar"
    ? `<c:barChart><c:barDir val="col"/><c:grouping val="clustered"/><c:varyColors val="0"/>${ser}<c:axId val="1"/><c:axId val="2"/></c:barChart>`
    : `<c:lineChart><c:grouping val="standard"/><c:varyColors val="0"/>${ser}<c:marker val="1"/><c:smooth val="0"/><c:axId val="1"/><c:axId val="2"/></c:lineChart>`;
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<c:chartSpace xmlns:c="${C_NS}" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <c:chart>
    <c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:pPr algn="ctr"/><a:r><a:rPr lang="ru-RU" sz="1200" dirty="0"/><a:t>${esc(title)}</a:t></a:r></a:p></c:rich></c:tx><c:overlay val="0"/></c:title>
    <c:plotArea><c:layout/>${plot}${axis(1, 2, "b", false)}${axis(2, 1, "l", kind === "bar")}</c:plotArea>
    <c:legend><c:legendPos val="b"/></c:legend>
    <c:plotVisOnly val="1"/>
  </c:chart>
</c:chartSpace>`;
}

export const CHARTS = {
  elo: chartXml({
    kind: "line",
    title: "Ожидание Эло",
    yTitle: "Ожидание хозяев",
    cats: ["−400", "−300", "−200", "−100", "0", "100", "200", "300", "400"],
    values: ["0.137", "0.220", "0.334", "0.471", "0.613", "0.738", "0.834", "0.899", "0.941"],
  }),
  bars: chartXml({
    kind: "bar",
    title: "Вероятности 1 / X / 2",
    yTitle: "Доля",
    cats: ["1 (хозяева)", "X (ничья)", "2 (гости)"],
    values: ["0.482", "0.244", "0.274"],
  }),
};

function drawing(relId, docPr) {
  const cx = 5200000;
  const cy = 3000000;
  return `<w:p>
    <w:pPr><w:jc w:val="center"/><w:spacing w:before="200" w:after="0" w:line="240" w:lineRule="auto"/></w:pPr>
    <w:r><w:drawing>
      <wp:inline distT="0" distB="0" distL="0" distR="0">
        <wp:extent cx="${cx}" cy="${cy}"/>
        <wp:effectExtent l="0" t="0" r="0" b="0"/>
        <wp:docPr id="${docPr}" name="Диаграмма ${docPr}"/>
        <wp:cNvGraphicFramePr/>
        <a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
          <a:graphicData uri="${C_NS}">
            <c:chart xmlns:c="${C_NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="${relId}"/>
          </a:graphicData>
        </a:graphic>
      </wp:inline>
    </w:drawing></w:r>
  </w:p>`;
}

function formulaParagraph(omml, num) {
  const tab = num
    ? `<w:tabs><w:tab w:val="center" w:pos="4670"/><w:tab w:val="right" w:pos="9350"/></w:tabs>`
    : "";
  const number = num
    ? `<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/><w:sz w:val="28"/></w:rPr><w:tab/></w:r>${omml}<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman"/><w:sz w:val="28"/></w:rPr><w:tab/><w:t>(${esc(num)})</w:t></w:r>`
    : omml;
  return `<w:p><w:pPr><w:spacing w:before="200" w:after="0" w:line="240" w:lineRule="auto"/>${tab}<w:jc w:val="${num ? "left" : "center"}"/></w:pPr>${number}</w:p>`;
}

export async function injectOfficeParts(buf, formulas) {
  const zip = await JSZip.loadAsync(buf);
  let xml = await zip.file("word/document.xml").async("string");
  if (!xml.includes("xmlns:m=")) {
    xml = xml.replace("<w:document ", `<w:document xmlns:m="${M_NS}" `);
  }
  if (!xml.includes("xmlns:c=")) {
    xml = xml.replace("<w:document ", `<w:document xmlns:c="${C_NS}" `);
  }

  const paragraphStart = (source, at) => {
    let i = at;
    while (i >= 0) {
      i = source.lastIndexOf("<w:p", i);
      if (i < 0) return -1;
      const next = source[i + 4];
      if (next === ">" || next === " ") return i;
      i -= 1;
    }
    return -1;
  };
  const replacePara = (source, marker, para) => {
    const at = source.indexOf(marker);
    if (at < 0) throw new Error(`Marker missing: ${marker}`);
    const start = paragraphStart(source, at);
    const end = source.indexOf("</w:p>", at);
    if (start < 0 || end < 0) throw new Error(`Paragraph bounds missing: ${marker}`);
    return source.slice(0, start) + para + source.slice(end + "</w:p>".length);
  };
  formulas.forEach((f, i) => {
    xml = replacePara(xml, `[[F${i}]]`, formulaParagraph(latexToOmml(f.latex), f.num));
  });

  let rels = await zip.file("word/_rels/document.xml.rels").async("string");
  let types = await zip.file("[Content_Types].xml").async("string");
  let next = 1;
  for (const m of rels.matchAll(/Id="rId(\d+)"/g)) next = Math.max(next, Number(m[1]) + 1);
  let docPr = 80;
  for (const [key, chart] of Object.entries(CHARTS)) {
    const marker = `[[C${key}]]`;
    if (!xml.includes(marker)) continue;
    const relId = `rId${next++}`;
    const part = `word/charts/chart-${key}.xml`;
    zip.file(part, chart);
    rels = rels.replace("</Relationships>", `<Relationship Id="${relId}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/chart" Target="charts/chart-${key}.xml"/></Relationships>`);
    if (!types.includes(`/word/charts/chart-${key}.xml`)) {
      types = types.replace("</Types>", `<Override PartName="/word/charts/chart-${key}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/></Types>`);
    }
    xml = replacePara(xml, marker, drawing(relId, docPr++));
  }

  zip.file("word/document.xml", xml);
  zip.file("word/_rels/document.xml.rels", rels);
  zip.file("[Content_Types].xml", types);
  return zip.generateAsync({ type: "nodebuffer" });
}
