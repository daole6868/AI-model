// Tab Mô hình: trạng thái Ollama, model gợi ý, tải về có tiến độ, model đã cài, Gemma 270M.
import { $, $$, h, esc, icon, getJSON, sendJSON, streamNDJSON, toast, fmtBytes, emit, on } from "./util.js";

// Chỉ dùng các tên model có trong tài liệu chính thức của Ollama.
const RECOMMENDED = [
  { name: "qwen3:8b", title: "Qwen3 8B", size: "≈ 5,2 GB", tags: [["Khuyên dùng", "accent"], ["Biết suy nghĩ", "info"]],
    desc: "Cân bằng tốt nhất cho card 8 GB: trả lời mạch lạc, tiếng Việt khá tốt, có chế độ suy nghĩ trước khi trả lời." },
  { name: "qwen3:4b", title: "Qwen3 4B", size: "≈ 2,5 GB", tags: [["Nhanh", "info"], ["Nhẹ", ""]],
    desc: "Bản nhỏ hơn của Qwen3: trả lời nhanh, tốn ít bộ nhớ, hợp khi cần phản hồi tức thì." },
  { name: "gemma4:e2b", title: "Gemma 4 E2B", size: null, tags: [["Google", ""], ["Đa ngôn ngữ", "info"]],
    desc: "Bản nhỏ trong dòng Gemma 4 của Google, hỗ trợ nhiều ngôn ngữ." },
  { name: "llama3.1:8b", title: "Llama 3.1 8B", size: "≈ 4,9 GB", tags: [["Meta", ""], ["Phổ biến", ""]],
    desc: "Model nổi tiếng của Meta, mạnh về tiếng Anh; tiếng Việt ở mức khá." },
];

let root, app;
let installed = [];
let ollamaErr = null;
const pulls = new Map(); // tên model -> {pct, done, total, status, controller}

export function init(el, shared) {
  root = el;
  app = shared;
  root.innerHTML = `
  <div class="page-inner">
    <div class="page-head"><h1>Mô hình</h1><p>Tải và quản lý các model AI chạy trên máy bạn. Model tải một lần, dùng mãi, không cần Internet khi trò chuyện.</p></div>
    <div class="card status-card" id="ollamaCard"></div>
    <h2 class="section-title">Gợi ý cho máy của bạn <span class="hint" id="gpuHint"></span></h2>
    <div class="model-grid" id="recGrid"></div>
    <h2 class="section-title">Đã cài trên máy</h2>
    <div class="card installed" id="instList"></div>
    <h2 class="section-title">Tải model khác <span class="hint">xem danh sách tại <a href="https://ollama.com/library" target="_blank" rel="noopener noreferrer">ollama.com/library</a></span></h2>
    <div class="card pull-row" id="customPull">
      <input type="text" id="customName" placeholder="Ví dụ: qwen3:14b" spellcheck="false" aria-label="Tên model">
      <button class="btn primary" type="button" id="customBtn">${icon("download")}Tải về</button>
      <div class="progress" id="customProg" hidden></div>
    </div>
    <h2 class="section-title">Gemma 270M tiếng Việt <span class="hint">model thử nghiệm của bài viết</span></h2>
    <div class="card status-card" id="gemmaCard"></div>
  </div>`;
  $("#customBtn", root).onclick = () => {
    const name = $("#customName", root).value.trim();
    if (!name) return $("#customName", root).focus();
    pull(name);
  };
  $("#customName", root).addEventListener("keydown", (e) => { if (e.key === "Enter") $("#customBtn", root).click(); });
  root.addEventListener("click", onClick);
  on("status", () => refresh());
}

export function onShow() {
  refresh();
}

async function refresh() {
  let data = { ollama: [], gemma: null };
  try { data = await getJSON("/api/models"); } catch {}
  installed = data.ollama || [];
  ollamaErr = data.ollama_error;
  drawOllama();
  drawRecommended();
  drawInstalled();
  drawGemma(data.gemma);
  drawCustomProgress();
}

function drawOllama() {
  const st = app.status || {};
  const ver = st.ollama?.version;
  const card = $("#ollamaCard", root);
  card.className = "card status-card " + (ver ? "ok" : "bad");
  card.innerHTML = ver
    ? `<div class="big-icon">${icon("check")}</div>
       <div class="txt"><b>Ollama đang chạy</b><p>Phiên bản ${esc(ver)} · ${installed.length} model đã cài. Sẵn sàng tải và chạy model trên GPU.</p></div>
       <div class="acts"><button class="btn" type="button" data-act="recheck">${icon("refresh")}Kiểm tra lại</button></div>`
    : `<div class="big-icon">${icon("alert")}</div>
       <div class="txt"><b>Chưa kết nối được Ollama</b>
         <p>Ollama là phần mềm miễn phí giúp chạy các model AI lớn trên GPU. Cần có Ollama để trò chuyện với model mạnh.</p>
         <ol><li>Bấm <b>Tải Ollama</b>, cài đặt như phần mềm bình thường (hoặc chạy lại <b>CHAY_WINDOWS.bat</b> và chọn Y).</li>
         <li>Mở ứng dụng Ollama (biểu tượng con lạc đà ở khay hệ thống).</li>
         <li>Bấm <b>Kiểm tra lại</b>.</li></ol></div>
       <div class="acts">
         <a class="btn primary" href="https://ollama.com/download" target="_blank" rel="noopener noreferrer">${icon("external")}Tải Ollama</a>
         <button class="btn" type="button" data-act="recheck">${icon("refresh")}Kiểm tra lại</button></div>`;
  const g = st.gpu || {};
  $("#gpuHint", root).textContent = g.state === "ok"
    ? `· ${g.name.replace(/^NVIDIA (GeForce )?/, "")} ${g.vram_gb} GB: model ≤ 8B chạy mượt trên GPU`
    : "";
}

function progressHTML(p) {
  const pct = p.total ? Math.min(100, (p.done / p.total) * 100) : 0;
  const left = p.total ? `${fmtBytes(p.done)} / ${fmtBytes(p.total)}` : esc(p.status || "Đang bắt đầu…");
  return `<div class="bar"><i style="width:${pct.toFixed(1)}%"></i></div>
    <small><span>${left}</span><span>${p.total ? pct.toFixed(0) + "%" : ""}</span></small>`;
}

function drawRecommended() {
  const have = new Set(installed.map((m) => m.name));
  const ok = !!app.status?.ollama?.version;
  $("#recGrid", root).innerHTML = RECOMMENDED.map((r) => {
    const p = pulls.get(r.name);
    const isIn = have.has(r.name);
    let foot;
    if (p) {
      foot = `<div class="progress">${progressHTML(p)}</div><button class="btn sm" type="button" data-cancel="${esc(r.name)}">${icon("x")}Hủy</button>`;
    } else if (isIn) {
      foot = `<span class="badge accent">${icon("check")} Đã cài</span>
        <button class="btn sm primary" type="button" data-use="${esc(r.name)}">${icon("chat")}Trò chuyện</button>`;
    } else {
      foot = `<button class="btn sm primary" type="button" data-pull="${esc(r.name)}" ${ok ? "" : "disabled title='Cần Ollama đang chạy'"}>${icon("download")}Tải về</button>
        ${r.size ? `<span class="badge">${r.size}</span>` : ""}`;
    }
    return `<article class="card model-card">
      <div class="mc-head"><div style="flex:1"><h3>${esc(r.title)}</h3><code>${esc(r.name)}</code></div></div>
      <div class="tags">${r.tags.map(([t, c]) => `<span class="badge ${c}">${t}</span>`).join("")}</div>
      <p>${esc(r.desc)}</p>
      <div class="mc-foot">${foot}</div>
    </article>`;
  }).join("");
}

function drawInstalled() {
  const box = $("#instList", root);
  if (!installed.length) {
    box.innerHTML = `<div class="inst-empty">${ollamaErr && !app.status?.ollama?.version ? "Chưa kết nối được Ollama." : "Chưa có model nào. Hãy tải một model ở mục Gợi ý phía trên."}</div>`;
    return;
  }
  box.innerHTML = `<div class="inst-row head"><span>Tên model</span><span>Tham số</span><span>Lượng tử</span><span>Dung lượng</span><span></span></div>` +
    installed.map((m) => `<div class="inst-row">
      <span class="nm" title="${esc(m.name)}">${esc(m.name)}</span>
      <span>${esc(m.params || "—")}</span><span>${esc(m.quant || "—")}</span><span>${fmtBytes(m.size)}</span>
      <span class="acts">
        <button class="btn sm primary" type="button" data-use="${esc(m.name)}">${icon("chat")}Trò chuyện</button>
        <button class="btn sm ghost" type="button" data-del="${esc(m.name)}" title="Xóa model" aria-label="Xóa ${esc(m.name)}">${icon("trash")}</button>
      </span></div>`).join("");
}

function drawCustomProgress() {
  const name = $("#customName", root).value.trim();
  const p = name && !RECOMMENDED.some((r) => r.name === name) ? pulls.get(name) : null;
  const box = $("#customProg", root);
  box.hidden = !p;
  if (p) box.innerHTML = progressHTML(p);
}

function drawGemma(g) {
  const card = $("#gemmaCard", root);
  if (!g) { card.innerHTML = ""; return; }
  const states = {
    unavailable: ["bad", "alert", "Chưa cài PyTorch", esc(g.error || ""), ""],
    idle: ["", "chip", "Chưa nạp", "Model nhỏ (270 triệu tham số) dùng cho tab So sánh. Lần đầu nạp sẽ tải khoảng 540 MB.",
      `<button class="btn primary" type="button" data-act="gemma-load">${icon("download")}Tải &amp; nạp model</button>`],
    loading: ["", "chip", "Đang tải / nạp model…", "Có thể mất vài phút ở lần đầu. Bạn vẫn dùng được các tab khác.", `<span class="spinner"></span>`],
    ready: ["ok", "check", "Sẵn sàng", `Đang chạy trên ${esc(g.device_name || "")} (${esc(g.dtype || "")}).`,
      `<button class="btn" type="button" data-act="goto-compare">${icon("compare")}Mở tab So sánh</button>`],
    error: ["bad", "alert", "Lỗi khi nạp model", esc(g.error || ""), `<button class="btn" type="button" data-act="gemma-load">${icon("refresh")}Thử lại</button>`],
  };
  const [cls, ic, title, desc, act] = states[g.state] || states.idle;
  card.className = "card status-card " + cls;
  card.innerHTML = `<div class="big-icon">${icon(ic)}</div>
    <div class="txt"><b>${title}</b><p>${desc}</p></div><div class="acts">${act}</div>`;
  if (g.state === "loading") setTimeout(refreshStatusSoon, 2000);
}

async function refreshStatusSoon() {
  try {
    const st = await getJSON("/api/status");
    app.status = st;
    drawGemma(st.gemma);
    if (st.gemma.state !== "loading") emit("status", st);
  } catch {}
}

async function onClick(e) {
  const t = e.target.closest("button, a");
  if (!t) return;
  if (t.dataset.pull) return pull(t.dataset.pull);
  if (t.dataset.cancel) { pulls.get(t.dataset.cancel)?.controller.abort(); return; }
  if (t.dataset.use) return emit("use-model", t.dataset.use);
  if (t.dataset.del) {
    if (!confirm(`Xóa model ${t.dataset.del}? Bạn có thể tải lại sau.`)) return;
    try { await sendJSON("/api/models/delete", "POST", { name: t.dataset.del }); toast("Đã xóa " + t.dataset.del); }
    catch (err) { toast(err.message); }
    emit("models-changed");
    return refresh();
  }
  const act = t.dataset.act;
  if (act === "recheck") {
    try { app.status = await getJSON("/api/status"); } catch {}
    await refresh();
    toast(app.status?.ollama?.version ? "Ollama đang chạy ✓" : "Vẫn chưa kết nối được Ollama");
  } else if (act === "gemma-load") {
    try { drawGemma(await sendJSON("/api/gemma/load", "POST", {})); } catch (err) { toast(err.message); }
  } else if (act === "goto-compare") {
    emit("goto", "compare");
  }
}

async function pull(name) {
  if (pulls.has(name)) return;
  if (!app.status?.ollama?.version) return toast("Cần mở Ollama trước khi tải model");
  const p = { done: 0, total: 0, status: "Đang bắt đầu…", controller: new AbortController(), parts: {} };
  pulls.set(name, p);
  drawRecommended();
  drawCustomProgress();
  let error = null, success = false, last = 0;
  try {
    await streamNDJSON("/api/models/pull", { name }, (o) => {
      if (o.error) error = o.error;
      if (o.status) p.status = o.status;
      if (o.status === "success") success = true;
      if (o.digest && o.total) {
        p.parts[o.digest] = { total: o.total, done: o.completed || 0 };
        p.total = Object.values(p.parts).reduce((a, x) => a + x.total, 0);
        p.done = Object.values(p.parts).reduce((a, x) => a + x.done, 0);
      }
      const now = performance.now();
      if (now - last > 250) { last = now; drawRecommended(); drawCustomProgress(); }
    }, p.controller.signal);
  } catch (err) {
    error = err.name === "AbortError" ? "Đã hủy (lần sau tải tiếp từ chỗ dừng)" : err.message;
  }
  pulls.delete(name);
  if (success) toast(`Đã tải xong ${name} ✓`);
  else if (error) toast(error.includes("file does not exist") ? `Không tìm thấy model "${name}". Kiểm tra lại tên.` : `${name}: ${error}`);
  emit("models-changed");
  await refresh();
}
