// Tab Tài liệu: tải bộ bài viết gốc về máy, đọc offline, xuất cả bộ thành .zip.
import { $, $$, h, esc, icon, getJSON, streamNDJSON, toast, fmtBytes, downloadText } from "./util.js";
import { render } from "./md.js";

let root;
let catalog = [];
let current = null;
const busyIds = new Set();
let downloadingAll = false;

export function init(el) {
  root = el;
  root.innerHTML = `
  <div class="docs-layout">
    <aside class="docs-side card">
      <div class="docs-top">
        <h2>Bộ tài liệu</h2>
        <p>Các bài viết gốc trong bài chia sẻ, kèm hình minh họa. Tải về một lần, đọc offline.</p>
        <div class="row">
          <button class="btn primary" type="button" id="dlAll">${icon("download")}Tải tất cả về máy</button>
        </div>
        <a class="btn" id="dlZip" href="/api/docs/export.zip" download="Bo-tai-lieu-AI-Viet.zip">${icon("box")}Lưu cả bộ ra máy (.zip)</a>
      </div>
      <div class="doc-list" id="docList"></div>
    </aside>
    <article class="reader card" id="reader"></article>
  </div>`;
  $("#dlAll", root).onclick = () => downloadDocs(null);
  $("#docList", root).addEventListener("click", (e) => {
    const b = e.target.closest("[data-doc]");
    if (b) open(b.dataset.doc);
  });
  $("#reader", root).addEventListener("click", (e) => {
    const t = e.target.closest("[data-act]");
    if (!t) return;
    if (t.dataset.act === "get") downloadDocs([current]);
    if (t.dataset.act === "md") saveMd();
  });
}

export async function onShow() {
  await load();
  if (!current) open(catalog[0]?.id);
}

async function load() {
  try { catalog = await getJSON("/api/docs"); } catch (e) { toast(e.message); }
  drawList();
}

function statusIcon(d) {
  if (busyIds.has(d.id)) return `<span class="spinner"></span>`;
  if (d.downloaded) return `<span class="badge accent" title="Đã có trên máy">${icon("check")}</span>`;
  return `<span class="badge" title="Chưa tải">${icon("download")}</span>`;
}

function drawList() {
  const groups = [...new Set(catalog.map((d) => d.group))];
  $("#docList", root).innerHTML = groups.map((g) => `<div class="doc-group">${esc(g)}</div>` +
    catalog.filter((d) => d.group === g).map((d) => `
      <button class="doc-item ${d.id === current ? "active" : ""}" type="button" data-doc="${esc(d.id)}">
        <span class="di-icon">${icon(d.kind === "bundled" ? "spark" : "file")}</span>
        <span class="di-txt"><b>${esc(d.title)}</b><small>${esc(d.author)}${d.downloaded && d.size ? " · " + fmtBytes(d.size) : ""}</small></span>
        <span class="st">${statusIcon(d)}</span>
      </button>`).join("")).join("");
  const missing = catalog.filter((d) => !d.downloaded).length;
  const btn = $("#dlAll", root);
  btn.disabled = downloadingAll;
  btn.innerHTML = downloadingAll ? `<span class="spinner"></span>Đang tải…`
    : missing ? `${icon("download")}Tải tất cả về máy (${missing})` : `${icon("refresh")}Tải lại bản mới nhất`;
}

async function open(id) {
  if (!id) return;
  current = id;
  drawList();
  const d = catalog.find((x) => x.id === id);
  const reader = $("#reader", root);
  const head = `<header class="reader-head">
      <div class="rt"><b>${esc(d.title)}</b><small>${esc(d.author)}</small></div>
      ${d.page ? `<a class="btn sm" href="${esc(d.page)}" target="_blank" rel="noopener noreferrer">${icon("external")}Trang gốc</a>` : ""}
      ${d.downloaded ? `<button class="btn sm" type="button" data-act="md">${icon("download")}Lưu .md</button>` : ""}
      ${d.downloaded && d.kind !== "bundled" ? `<button class="btn sm ghost" type="button" data-act="get" title="Tải lại bản mới nhất">${icon("refresh")}</button>` : ""}
    </header>`;
  if (!d.downloaded) {
    reader.innerHTML = head + `<div class="reader-scroll"><div class="reader-empty">
      <div class="big-icon">${icon("download")}</div><b>Bài này chưa có trên máy</b>
      <p>${esc(d.summary || "")}</p>
      <button class="btn primary" type="button" data-act="get" ${busyIds.has(id) ? "disabled" : ""}>${busyIds.has(id) ? `<span class="spinner"></span>Đang tải…` : `${icon("download")}Tải bài này`}</button>
    </div></div>`;
    return;
  }
  reader.innerHTML = head + `<div class="reader-scroll"><div class="reader-body md"><p style="color:var(--muted)">Đang mở…</p></div></div>`;
  try {
    const doc = await getJSON(`/api/docs/${id}`);
    if (current !== id) return;
    $(".reader-body", reader).innerHTML = render(doc.markdown || "", { images: true, base: `/docs-assets/${id}/` });
    $(".reader-scroll", reader).scrollTop = 0;
  } catch (e) {
    $(".reader-body", reader).textContent = "Không mở được: " + e.message;
  }
}

async function downloadDocs(ids) {
  if (downloadingAll) return;
  const targets = ids || catalog.filter((d) => d.kind !== "bundled").map((d) => d.id);
  if (!ids) downloadingAll = true;
  targets.forEach((i) => busyIds.add(i));
  drawList();
  if (current && targets.includes(current)) open(current);
  let ok = 0, bad = 0;
  try {
    await streamNDJSON("/api/docs/download", { ids: targets }, (o) => {
      if (o.status === "ok" || o.status === "error") {
        busyIds.delete(o.id);
        const d = catalog.find((x) => x.id === o.id);
        if (o.status === "ok") { ok++; if (d) { d.downloaded = true; d.size = o.size; } }
        else { bad++; toast(`Lỗi tải "${d?.title || o.id}": ${o.error}`); }
        drawList();
        if (o.id === current) open(current);
      }
    });
  } catch (e) {
    toast("Không tải được: " + e.message);
  }
  targets.forEach((i) => busyIds.delete(i));
  downloadingAll = false;
  await load();
  if (current) open(current);
  if (ok) toast(`Đã tải ${ok} tài liệu${bad ? `, lỗi ${bad}` : ""} ✓`);
}

async function saveMd() {
  try {
    const doc = await getJSON(`/api/docs/${current}`);
    downloadText(`${current}.md`, doc.markdown || "");
  } catch (e) { toast(e.message); }
}
