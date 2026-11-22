// Tab Trò chuyện: chat với AI như ChatGPT, có lịch sử, chọn model, xem suy nghĩ.
import { $, h, esc, icon, getJSON, sendJSON, streamNDJSON, stopAll, toast, copyText, fmtAgo, downloadText, autosize, emit, on } from "./util.js";
import { render } from "./md.js";
import { save as saveSettings } from "./settings.js";

const GEMMA = "gemma-vi-steer";
const SUGGEST = [
  ["Giải thích dễ hiểu", "Giải thích trí tuệ nhân tạo là gì cho học sinh lớp 8, kèm ví dụ đời thường."],
  ["Viết giúp tôi", "Viết một email xin nghỉ phép 2 ngày gửi quản lý, giọng lịch sự và ngắn gọn."],
  ["Lập kế hoạch", "Lập kế hoạch học tiếng Anh trong 30 ngày cho người mới bắt đầu, mỗi ngày 30 phút."],
  ["Lập trình", "Viết hàm Python kiểm tra một số có phải số nguyên tố không, kèm giải thích từng bước."],
];

let root, app;
let models = { ollama: [], gemma: null };
let convs = [];
let conv = null;
let busy = false;
let controller = null;
let stick = true;

const modelLabel = (name) => (name === GEMMA ? "Gemma 270M tiếng Việt" : name || "AI");

export function init(el, shared) {
  root = el;
  app = shared;
  root.innerHTML = `
  <div class="chat-layout">
    <aside class="conv-panel card" aria-label="Lịch sử trò chuyện">
      <button class="btn primary wide" id="newConv" type="button">${icon("plus")}Cuộc trò chuyện mới</button>
      <div class="conv-search">${icon("search")}<input type="text" id="convSearch" placeholder="Tìm cuộc trò chuyện…" aria-label="Tìm cuộc trò chuyện"></div>
      <div class="conv-list" id="convList"></div>
    </aside>
    <section class="chat-main card">
      <header class="chat-head">
        <select id="chatModel" aria-label="Chọn model"></select>
        <div class="chat-title" id="chatTitle"></div>
        <button class="icon-btn" id="exportConv" type="button" title="Tải cuộc trò chuyện (.md)" aria-label="Tải cuộc trò chuyện">${icon("download")}</button>
      </header>
      <div class="chat-scroll" id="chatScroll"><div class="thread" id="thread"></div></div>
      <footer class="chat-compose">
        <div class="compose-box">
          <textarea id="chatInput" rows="1" placeholder="Nhắn cho AI… (Enter để gửi, Shift+Enter để xuống dòng)" aria-label="Nội dung tin nhắn"></textarea>
          <button class="send-btn" id="chatSend" type="button" aria-label="Gửi">${icon("send")}</button>
        </div>
        <div class="compose-hint">AI chạy trên máy bạn và có thể sai. Hãy kiểm tra lại thông tin quan trọng.</div>
      </footer>
    </section>
  </div>`;

  const input = $("#chatInput", root);
  const ph = () => (input.placeholder = innerWidth < 700 ? "Nhắn cho AI…" : "Nhắn cho AI… (Enter để gửi, Shift+Enter để xuống dòng)");
  ph();
  addEventListener("resize", ph);
  input.addEventListener("input", () => autosize(input));
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
  });
  $("#chatSend", root).onclick = () => (busy ? stop() : send());
  $("#newConv", root).onclick = () => newConv();
  $("#convSearch", root).addEventListener("input", renderConvList);
  $("#exportConv", root).onclick = exportConv;
  $("#chatModel", root).onchange = (e) => saveSettings({ default_model: e.target.value }, true);
  const sc = $("#chatScroll", root);
  sc.addEventListener("scroll", () => { stick = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 140; });

  $("#convList", root).addEventListener("click", (e) => {
    const del = e.target.closest("[data-del]");
    if (del) return deleteConv(del.dataset.del);
    const open = e.target.closest("[data-open]");
    if (open) openConv(open.dataset.open);
  });
  $("#thread", root).addEventListener("click", (e) => {
    const q = e.target.closest("[data-q]");
    if (q) return send(q.dataset.q);
    if (e.target.closest("[data-goto-models]")) emit("goto", "models");
  });

  on("status", () => loadModels());
  on("models-changed", () => loadModels());
  on("convs-cleared", () => {
    convs = [];
    if (!busy) conv = { id: null, title: "", model: "", messages: [] };
    renderConvList();
    renderThread();
  });
  on("use-model", async (name) => {
    await loadModels();
    const sel = $("#chatModel", root);
    if ([...sel.options].some((o) => o.value === name)) { sel.value = name; saveSettings({ default_model: name }, true); }
    newConv();
    emit("goto", "chat");
  });

  conv = { id: null, title: "", model: "", messages: [] };
  loadModels();
  loadConvs();
  renderThread();
}

export function onShow() {
  loadModels();
  setTimeout(() => $("#chatInput", root)?.focus(), 30);
}

// ---------- Model ----------
async function loadModels() {
  try { models = await getJSON("/api/models"); } catch { models = { ollama: [], gemma: null }; }
  const sel = $("#chatModel", root);
  const want = sel.value || conv?.model || app.settings?.default_model || "";
  let html = "";
  if (models.ollama.length) {
    html += `<optgroup label="Model trên máy (Ollama)">${models.ollama.map((m) =>
      `<option value="${esc(m.name)}">${esc(m.name)}${m.params ? " · " + esc(m.params) : ""}</option>`).join("")}</optgroup>`;
  }
  if (models.gemma && models.gemma.state !== "unavailable") {
    html += `<optgroup label="Thử nghiệm"><option value="${GEMMA}">Gemma 270M tiếng Việt (nhỏ, để thử)</option></optgroup>`;
  }
  if (!html) html = `<option value="">Chưa có model nào</option>`;
  sel.innerHTML = html;
  const values = [...sel.options].map((o) => o.value);
  sel.value = values.includes(want) ? want : values[0] || "";
  if (conv && !conv.messages.length && !busy) renderThread();
}

// ---------- Danh sách cuộc trò chuyện ----------
async function loadConvs() {
  try { convs = await getJSON("/api/convs"); } catch { convs = []; }
  renderConvList();
}

function renderConvList() {
  const box = $("#convList", root);
  const q = $("#convSearch", root).value.trim().toLowerCase();
  const list = convs.filter((c) => !q || c.title.toLowerCase().includes(q));
  if (!list.length) {
    box.innerHTML = `<div class="conv-empty">${q ? "Không tìm thấy cuộc trò chuyện nào." : "Chưa có cuộc trò chuyện nào.<br>Hãy gửi tin nhắn đầu tiên!"}</div>`;
    return;
  }
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const t0 = today.getTime() / 1000;
  const groups = [["Hôm nay", (c) => c.updated >= t0], ["7 ngày qua", (c) => c.updated >= t0 - 6 * 86400], ["Cũ hơn", () => true]];
  const used = new Set();
  let html = "";
  for (const [label, test] of groups) {
    const items = list.filter((c) => !used.has(c.id) && test(c));
    if (!items.length) continue;
    items.forEach((c) => used.add(c.id));
    html += `<div class="conv-group">${label}</div>` + items.map((c) => `
      <div class="conv-item ${conv?.id === c.id ? "active" : ""}">
        <button class="ct" type="button" data-open="${esc(c.id)}"><b>${esc(c.title)}</b><small>${esc(modelLabel(c.model))} · ${fmtAgo(c.updated)}</small></button>
        <button class="del" type="button" data-del="${esc(c.id)}" title="Xóa" aria-label="Xóa cuộc trò chuyện">${icon("trash")}</button>
      </div>`).join("");
  }
  box.innerHTML = html;
}

async function openConv(id) {
  if (busy) return toast("Đang trả lời, hãy bấm Dừng trước.");
  try { conv = await getJSON(`/api/convs/${id}`); } catch (e) { return toast(e.message); }
  const sel = $("#chatModel", root);
  if ([...sel.options].some((o) => o.value === conv.model)) sel.value = conv.model;
  renderConvList();
  renderThread();
}

function newConv() {
  if (busy) return toast("Đang trả lời, hãy bấm Dừng trước.");
  conv = { id: null, title: "", model: $("#chatModel", root).value, messages: [] };
  renderConvList();
  renderThread();
  $("#chatInput", root).focus();
}

async function deleteConv(id) {
  if (!confirm("Xóa cuộc trò chuyện này? Không thể hoàn tác.")) return;
  try { await sendJSON(`/api/convs/${id}`, "DELETE"); } catch (e) { return toast(e.message); }
  if (conv?.id === id && !busy) { conv = { id: null, title: "", model: "", messages: [] }; renderThread(); }
  await loadConvs();
  toast("Đã xóa");
}

async function saveConv() {
  const body = { title: conv.title, model: conv.model, messages: conv.messages };
  try {
    const saved = conv.id ? await sendJSON(`/api/convs/${conv.id}`, "PUT", body) : await sendJSON("/api/convs", "POST", body);
    conv.id = saved.id;
    await loadConvs();
  } catch (e) {
    toast("Không lưu được lịch sử: " + e.message);
  }
}

function exportConv() {
  if (!conv.messages.length) return toast("Cuộc trò chuyện đang trống");
  let md = `# ${conv.title || "Cuộc trò chuyện"}\n\n`;
  for (const m of conv.messages) {
    md += m.role === "user" ? `### Bạn\n\n${m.content}\n\n` : `### AI (${modelLabel(m.meta?.model)})\n\n${m.content}\n\n`;
  }
  const name = (conv.title || "tro-chuyen").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/g, "d").replace(/Đ/g, "D")
    .replace(/[^A-Za-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 50) || "tro-chuyen";
  downloadText(`${name}.md`, md);
}

// ---------- Hiển thị cuộc trò chuyện ----------
function welcomeHTML() {
  let notice = "";
  if (!models.ollama.length) {
    const running = !!app.status?.ollama?.version;
    notice = `<div class="notice">${icon("alert")}<div>
      <b>${running ? "Chưa có model AI nào trên máy" : "Ollama chưa chạy"}</b>
      <p>${running
        ? "Vào tab Mô hình để tải một model (khuyên dùng <b>qwen3:8b</b> cho card 8 GB). Tải một lần, dùng mãi."
        : "Ollama là phần mềm giúp chạy các model AI lớn trên GPU. Hãy mở ứng dụng Ollama, hoặc vào tab Mô hình để xem cách cài."}
      ${models.gemma && models.gemma.state !== "unavailable" ? " Trong lúc chờ, bạn vẫn có thể thử model nhỏ Gemma 270M." : ""}</p>
      <button class="btn sm primary" type="button" data-goto-models>${icon("box")}Đi tới tab Mô hình</button>
    </div></div>`;
  }
  return `<div class="welcome">
    ${notice}
    <div class="big-logo">Vi</div>
    <h2>Xin chào! Mình có thể giúp gì cho bạn?</h2>
    <p>Trò chuyện với AI chạy ngay trên máy tính của bạn. Câu hỏi không bị gửi lên Internet.</p>
    <div class="suggest">${SUGGEST.map(([t, q]) => `<button type="button" data-q="${esc(q)}"><b>${t}</b><span>${esc(q)}</span></button>`).join("")}</div>
  </div>`;
}

function userTurn(m) {
  const el = h(`<div class="turn user"><div class="bubble"></div></div>`);
  el.firstElementChild.textContent = m.content;
  return el;
}

function thinkBox(text, secs, open) {
  const d = h(`<details class="think"><summary>${icon("brain")}<span></span></summary><div class="think-text"></div></details>`);
  d.open = !!open;
  d.querySelector("span").textContent = secs == null ? "Đang suy nghĩ…" : `Đã suy nghĩ ${secs.toLocaleString("vi-VN", { maximumFractionDigits: 1 })} giây · xem`;
  d.querySelector(".think-text").textContent = text;
  return d;
}

function aiTurn(m, isLast) {
  const el = h(`<div class="turn ai"><div class="avatar">AI</div><div class="ai-body">
    <div class="ai-model"></div><div class="md"></div><div class="ai-actions"></div></div></div>`);
  $(".ai-model", el).textContent = modelLabel(m.meta?.model);
  if (m.thinking) $(".md", el).before(thinkBox(m.thinking, m.meta?.think_secs ?? null, false));
  $(".md", el).innerHTML = render(m.content);
  const acts = $(".ai-actions", el);
  const copy = h(`<button class="btn ghost sm" type="button">${icon("copy")}Sao chép</button>`);
  copy.onclick = () => copyText(m.content);
  acts.append(copy);
  if (isLast) {
    const re = h(`<button class="btn ghost sm" type="button">${icon("refresh")}Tạo lại</button>`);
    re.onclick = regenerate;
    acts.append(re);
  }
  if (m.meta?.tokens) {
    acts.append(h(`<span class="stat">${m.meta.tokens} token${m.meta.tps ? ` · ${m.meta.tps} token/giây` : ""}</span>`));
  }
  return el;
}

function errorTurn(err) {
  let hint = "";
  if (/kết nối được Ollama|Connection refused|URLError/i.test(err)) hint = "Hãy mở ứng dụng Ollama (biểu tượng ở khay hệ thống) rồi bấm Thử lại.";
  else if (/not found|không tìm thấy/i.test(err)) hint = "Model này chưa được tải. Vào tab Mô hình để tải, rồi thử lại.";
  else if (/memory|VRAM|out of/i.test(err)) hint = "Máy không đủ bộ nhớ cho model này. Hãy thử model nhỏ hơn hoặc giảm Độ dài ngữ cảnh trong Cài đặt.";
  const el = h(`<div class="turn ai"><div class="avatar">!</div><div class="ai-body">
    <div class="err-box"><b>Không nhận được câu trả lời</b><p></p></div>
    <div class="ai-actions"><button class="btn sm" type="button">${icon("refresh")}Thử lại</button></div></div></div>`);
  $("p", el).textContent = hint ? `${err}. ${hint}` : err;
  $("button", el).onclick = () => {
    if (busy) return;
    el.remove();
    conv.messages.at(-1)?.role === "assistant" ? regenerate() : generate();
  };
  return el;
}

function renderThread() {
  const t = $("#thread", root);
  $("#chatTitle", root).textContent = conv.title || "Cuộc trò chuyện mới";
  if (!conv.messages.length) {
    t.innerHTML = welcomeHTML();
    return;
  }
  t.innerHTML = "";
  const lastAi = conv.messages.length - 1;
  conv.messages.forEach((m, i) => t.append(m.role === "user" ? userTurn(m) : aiTurn(m, i === lastAi)));
  scrollBottom(true);
}

function scrollBottom(force) {
  const sc = $("#chatScroll", root);
  if (force || stick) sc.scrollTop = sc.scrollHeight;
}

// ---------- Gửi & nhận ----------
function setSendState() {
  const b = $("#chatSend", root);
  b.classList.toggle("stop", busy);
  b.innerHTML = icon(busy ? "stop" : "send");
  b.setAttribute("aria-label", busy ? "Dừng" : "Gửi");
  b.title = busy ? "Dừng" : "Gửi";
}

async function send(textArg) {
  if (busy) return;
  const input = $("#chatInput", root);
  const text = (textArg ?? input.value).trim();
  if (!text) return input.focus();
  if (!$("#chatModel", root).value) {
    toast("Chưa có model để trò chuyện. Hãy tải model ở tab Mô hình.");
    return emit("goto", "models");
  }
  input.value = "";
  autosize(input);
  if (!conv.messages.length) {
    const one = text.replace(/\s+/g, " ");
    conv.title = one.length > 60 ? one.slice(0, 58).trimEnd() + "…" : one;
  }
  conv.messages.push({ role: "user", content: text });
  stick = true;
  renderThread();
  await generate();
}

async function regenerate() {
  if (busy) return;
  if (conv.messages.at(-1)?.role === "assistant") conv.messages.pop();
  renderThread();
  await generate();
}

function stop() {
  controller?.abort();
  stopAll();
}

async function generate() {
  const model = $("#chatModel", root).value;
  conv.model = model;
  const history = conv.messages.map((m) => ({ role: m.role, content: m.content }));
  const view = h(`<div class="turn ai"><div class="avatar">AI</div><div class="ai-body">
    <div class="ai-model"></div><div class="waiting"><span class="typing"><i></i><i></i><i></i></span><span>Đang chờ model…</span></div>
    <div class="md streaming"></div></div></div>`);
  $(".ai-model", view).textContent = modelLabel(model);
  $("#thread", root).append(view);
  scrollBottom(true);

  busy = true;
  setSendState();
  controller = new AbortController();
  let text = "", thinking = "", err = null, raf = 0, thinkStart = null, thinkSecs = null;
  const meta = { model };
  let thinkEl = null;

  const paint = () => {
    raf = 0;
    if (thinking && !thinkEl) {
      thinkEl = thinkBox("", null, true);
      $(".md", view).before(thinkEl);
    }
    if (thinkEl) {
      $(".think-text", thinkEl).textContent = thinking;
      const tt = $(".think-text", thinkEl);
      tt.scrollTop = tt.scrollHeight;
      if (thinkSecs != null && thinkEl.open && text) {
        thinkEl.open = false;
        $("summary span", thinkEl).textContent = `Đã suy nghĩ ${thinkSecs.toLocaleString("vi-VN", { maximumFractionDigits: 1 })} giây · xem`;
      }
    }
    if (text || thinking) $(".waiting", view)?.remove();
    if (text) $(".md", view).innerHTML = render(text);
    scrollBottom(false);
  };

  const options = model === GEMMA ? { scale: 1, temperature: 0, repetition_penalty: 1.1, max_new_tokens: 1024 } : {};
  try {
    await streamNDJSON("/api/chat", { model, messages: history, options }, (o) => {
      if (o.th) { if (thinkStart === null) thinkStart = performance.now(); thinking += o.th; }
      if (o.t) {
        if (thinkStart !== null && thinkSecs === null) thinkSecs = (performance.now() - thinkStart) / 1000;
        text += o.t;
      }
      if (o.status) { const w = $(".waiting span:last-child", view); if (w) w.textContent = o.status; }
      if (o.error) err = o.error;
      if (o.done) Object.assign(meta, { tokens: o.tokens, tps: o.tps, secs: o.secs });
      if (!raf) raf = requestAnimationFrame(paint);
    }, controller.signal);
  } catch (e) {
    if (e.name !== "AbortError") err = e.message;
  }
  if (raf) cancelAnimationFrame(raf);
  if (thinkStart !== null && thinkSecs === null) thinkSecs = (performance.now() - thinkStart) / 1000;
  busy = false;
  controller = null;
  setSendState();

  if (text.trim() || thinking.trim()) {
    const msg = { role: "assistant", content: text.trim() || "_(Model chỉ suy nghĩ mà chưa kịp trả lời.)_", meta };
    if (thinking.trim()) { msg.thinking = thinking.trim(); meta.think_secs = Math.round(thinkSecs * 10) / 10; }
    conv.messages.push(msg);
    renderThread();
    await saveConv();
  } else {
    view.remove();
    if (!err) err = "Đã dừng trước khi model kịp trả lời";
  }
  if (err) {
    $("#thread", root).append(errorTurn(err));
    scrollBottom(true);
  }
  $("#chatInput", root).focus();
}
