// Trình hiển thị Markdown gọn nhẹ, an toàn (mọi HTML trong nội dung đều bị vô hiệu hóa).
import { esc } from "./util.js";

const CALLOUT = { note: "Ghi chú", tip: "Mẹo", caution: "Lưu ý", warning: "Lưu ý", danger: "Cảnh báo", important: "Quan trọng" };

function safeUrl(u, opt) {
  u = u.trim().replace(/^<|>$/g, "");
  if (/^https?:\/\//i.test(u) || /^mailto:/i.test(u)) return u;
  if (opt.base && /^[A-Za-z0-9._\-/%]+$/.test(u) && !u.includes("..") && !u.startsWith("/")) return opt.base + u;
  return null;
}

function inline(text, opt) {
  const codes = [];
  let s = text.replace(/`([^`\n]+)`/g, (_, c) => { codes.push(c); return `\u0000${codes.length - 1}\u0000`; });
  s = esc(s);
  // hình ảnh
  s = s.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)/g, (m, alt, src) => {
    const url = opt.images ? safeUrl(src.replace(/&amp;/g, "&"), opt) : null;
    return url ? `<img src="${esc(url)}" alt="${alt}" loading="lazy">` : (alt ? `[hình: ${alt}]` : "");
  });
  // liên kết
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)/g, (m, label, href) => {
    const url = safeUrl(href.replace(/&amp;/g, "&"), { ...opt, base: opt.linkBase });
    return url ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${label}</a>` : label;
  });
  // đường link trần
  s = s.replace(/(^|[\s(])(https?:\/\/[^\s<]+[^\s<.,;:!?)'"])/g, (m, pre, url) =>
    `${pre}<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`);
  s = s.replace(/\*\*([^*\n]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_\n]+?)__/g, "<strong>$1</strong>")
    .replace(/(^|[^*\w])\*(?!\s)([^*\n]+?)\*(?!\*)/g, "$1<em>$2</em>")
    .replace(/(^|[^_\w])_(?!\s)([^_\n]+?)_(?![_\w])/g, "$1<em>$2</em>")
    .replace(/~~([^~\n]+?)~~/g, "<del>$1</del>");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${esc(codes[+i])}</code>`);
}

const RE_FENCE = /^\s*(`{3,}|~{3,})\s*([\w+#.-]*)/;
const RE_HEAD = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const RE_HR = /^\s*([-*_])(\s*\1){2,}\s*$/;
const RE_ITEM = /^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$/;
const RE_TSEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
const RE_CALLOUT = /^:::(\w+)(?:\[(.*)\])?\s*$/;

function isBlockStart(lines, i) {
  const l = lines[i];
  return RE_FENCE.test(l) || RE_HEAD.test(l) || RE_HR.test(l) || /^\s*>/.test(l) || RE_ITEM.test(l) ||
    RE_CALLOUT.test(l) || (l.includes("|") && i + 1 < lines.length && RE_TSEP.test(lines[i + 1]));
}

function splitRow(r) {
  return r.trim().replace(/^\|/, "").replace(/\|$/, "").split(/(?<!\\)\|/).map((c) => c.trim().replace(/\\\|/g, "|"));
}

function codeBlock(code, lang) {
  return `<div class="codeblock"><div class="code-head"><span>${esc(lang || "code")}</span><button type="button" data-copy-code>Sao chép</button></div><pre><code>${esc(code)}</code></pre></div>`;
}

function parseList(lines, i, opt) {
  const first = lines[i].match(RE_ITEM);
  const indent = first[1].length;
  const ordered = /\d/.test(first[2]);
  const start = ordered ? parseInt(first[2], 10) : 1;
  const items = [];
  while (i < lines.length) {
    const l = lines[i];
    const m = l.match(RE_ITEM);
    if (m && m[1].length === indent && /\d/.test(m[2]) === ordered) { items.push([m[3]]); i++; continue; }
    if (m && m[1].length > indent && items.length) {
      const [html, ni] = parseList(lines, i, opt);
      items[items.length - 1].push({ html });
      i = ni;
      continue;
    }
    if (!l.trim()) {
      let j = i + 1;
      while (j < lines.length && !lines[j].trim()) j++;
      if (j < lines.length) {
        const mm = lines[j].match(RE_ITEM);
        const ind = lines[j].match(/^\s*/)[0].length;
        if (mm && ind === indent && /\d/.test(mm[2]) === ordered) { i = j; continue; }
        if (ind > indent) { i = j; continue; }
      }
      break;
    }
    const ind = l.match(/^\s*/)[0].length;
    if (!m && ind > indent && items.length) {
      if (RE_FENCE.test(l)) {
        const fm = l.match(RE_FENCE);
        const buf = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith(fm[1])) { buf.push(lines[i].slice(Math.min(ind, lines[i].match(/^\s*/)[0].length))); i++; }
        i++;
        items[items.length - 1].push({ html: codeBlock(buf.join("\n"), fm[2]) });
      } else {
        items[items.length - 1].push(l.trim());
        i++;
      }
      continue;
    }
    break;
  }
  const tag = ordered ? "ol" : "ul";
  const lis = items.map((parts) => {
    let html = "", prevText = false;
    for (const p of parts) {
      if (typeof p === "string") { html += (prevText ? "<br>" : "") + inline(p, opt); prevText = true; }
      else { html += p.html; prevText = false; }
    }
    return `<li>${html}</li>`;
  }).join("");
  return [`<${tag}${ordered && start !== 1 ? ` start="${start}"` : ""}>${lis}</${tag}>`, i];
}

export function render(src, opt = {}) {
  const lines = String(src ?? "").replace(/\r\n?/g, "\n").split("\n");
  const out = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    let m;
    if ((m = line.match(RE_FENCE))) {
      const fence = m[1], buf = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith(fence)) { buf.push(lines[i]); i++; }
      i++;
      out.push(codeBlock(buf.join("\n"), m[2]));
      continue;
    }
    if ((m = line.match(RE_CALLOUT))) {
      const buf = [];
      i++;
      while (i < lines.length && !/^:::\s*$/.test(lines[i])) { buf.push(lines[i]); i++; }
      i++;
      const type = m[1].toLowerCase();
      out.push(`<div class="callout ${esc(type)}"><div class="callout-title">${esc(m[2] || CALLOUT[type] || "Ghi chú")}</div><div>${render(buf.join("\n"), opt)}</div></div>`);
      continue;
    }
    if (!line.trim()) { i++; continue; }
    if ((m = line.match(RE_HEAD))) { const n = m[1].length; out.push(`<h${n}>${inline(m[2], opt)}</h${n}>`); i++; continue; }
    if (RE_HR.test(line)) { out.push("<hr>"); i++; continue; }
    if (line.includes("|") && i + 1 < lines.length && RE_TSEP.test(lines[i + 1])) {
      const head = splitRow(line);
      const al = splitRow(lines[i + 1]).map((c) => (c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : ""));
      i += 2;
      const rows = [];
      while (i < lines.length && lines[i].includes("|") && lines[i].trim()) { rows.push(splitRow(lines[i])); i++; }
      const a = (k) => (al[k] ? ` style="text-align:${al[k]}"` : "");
      out.push(`<div class="table-wrap"><table><thead><tr>${head.map((c, k) => `<th${a(k)}>${inline(c, opt)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${head.map((_, k) => `<td${a(k)}>${inline(r[k] ?? "", opt)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`);
      continue;
    }
    if (/^\s*>/.test(line)) {
      const buf = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
      out.push(`<blockquote>${render(buf.join("\n"), opt)}</blockquote>`);
      continue;
    }
    if (RE_ITEM.test(line)) { const [html, ni] = parseList(lines, i, opt); out.push(html); i = ni; continue; }
    const buf = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines, i)) { buf.push(lines[i]); i++; }
    const img = buf.length === 1 && buf[0].trim().match(/^!\[([^\]]*)\]\(([^)\s]+)\)$/);
    if (img && opt.images) {
      const tag = inline(buf[0].trim(), opt);
      out.push(`<figure>${tag}${img[1] ? `<figcaption>${esc(img[1])}</figcaption>` : ""}</figure>`);
    } else {
      out.push(`<p>${buf.map((l) => inline(l.trim(), opt)).join("<br>")}</p>`);
    }
  }
  return out.join("\n");
}

// Nút "Sao chép" trong khối code (gắn một lần cho cả trang).
document.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-copy-code]");
  if (!b) return;
  const code = b.closest(".codeblock").querySelector("code").textContent;
  try { await navigator.clipboard.writeText(code); b.textContent = "Đã chép ✓"; }
  catch { b.textContent = "Lỗi"; }
  setTimeout(() => (b.textContent = "Sao chép"), 1500);
});
