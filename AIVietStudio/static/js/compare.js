// Tab So sánh Gemma: Gemma-3-270M gốc và bản thêm vector tiếng Việt, trả lời cạnh nhau.
import { $, $$, h, esc, icon, getJSON, sendJSON, streamNDJSON, stopAll, toast, copyText, autosize, isVi, local, on, emit } from "./util.js";
import { render } from "./md.js";

const GEMMA = "gemma-vi-steer";
const INSTR = "Hãy trả lời bằng tiếng Việt.";
const EXAMPLES = [
  "Describe the feeling of winning a big award.",
  "List three ways to conserve water.",
  "Explain why the sky is blue.",
  "Give me some tips for learning a new language.",
  "Viết một bài thơ ngắn về mùa thu Hà Nội.",
];

let root;
let busy = false;
let controller = null;
const COLS = {};

export function init(el) {
  root = el;
  root.innerHTML = `
  <div class="cmp-layout">
    <aside class="cmp-side card">
      <h2>So sánh Gemma</h2>
      <p class="lead">Hỏi một lần, xem Gemma-3-270M gốc và bản "nghe lời tiếng Việt" (thêm đúng 640 con số) trả lời cạnh nhau.</p>
      <div class="hint" id="gState"></div>
      <div class="group">
        <div class="group-label">Chế độ</div>
        <div class="segmented" id="cmpMode">
          <button type="button" data-mode="compare">So sánh</button>
          <button type="button" data-mode="steer">Bản Việt</button>
          <button type="button" data-mode="base">Bản gốc</button>
        </div>
      </div>
      <div class="group">
        <label class="group-label" for="cScale">Độ mạnh vector tiếng Việt <output id="cScaleOut"></output></label>
        <input type="range" id="cScale" min="-2" max="3" step="0.1">
        <div class="ticks"><span>−2</span><span>0 · gốc</span><span>1 · tác giả</span><span>3</span></div>
      </div>
      <div class="group">
        <label class="group-label" for="cMax">Độ dài tối đa <output id="cMaxOut"></output></label>
        <input type="range" id="cMax" min="64" max="2048" step="64">
      </div>
      <div class="group">
        <label class="group-label" for="cTemp">Độ sáng tạo <output id="cTempOut"></output></label>
        <input type="range" id="cTemp" min="0" max="1.5" step="0.05">
      </div>
      <div class="group">
        <label class="group-label" for="cRep">Chống lặp ý <output id="cRepOut"></output></label>
        <input type="range" id="cRep" min="1" max="1.5" step="0.05">
        <p class="hint">1.00 = giống cách tác giả đo. Tăng nếu model nói lặp.</p>
      </div>
      <label class="switch"><input type="checkbox" id="cInstr"><span class="track"></span>
        <span>Tự thêm lời dặn tiếng Việt<em>Thêm vào cuối mỗi câu hỏi</em></span></label>
      <button class="btn wide" type="button" id="cNew">${icon("plus")}Làm mới</button>
    </aside>
    <section class="cmp-main">
      <div class="cmp-cols" id="cmpCols">
        <article class="cmp-col base card" data-col="base">
          <header class="cmp-head"><span class="sw"></span><div><h3>Gemma gốc</h3><small>google/gemma-3-270m-it</small></div>
            <span class="sp"></span><span class="badge" data-stat>VI 0/0</span><span class="badge">×0</span></header>
          <div class="cmp-body"></div>
        </article>
        <article class="cmp-col steer card" data-col="steer">
          <header class="cmp-head"><span class="sw"></span><div><h3>Bản tiếng Việt</h3><small>gemma-3-270m-it-vi-steer</small></div>
            <span class="sp"></span><span class="badge" data-stat>VI 0/0</span><span class="badge accent" id="cScaleChip"></span></header>
          <div class="cmp-body"></div>
        </article>
      </div>
      <div class="cmp-compose card">
        <div class="row">
          <textarea class="field" id="cInput" rows="1" placeholder="Nhập câu hỏi (tiếng Anh hoặc tiếng Việt)… Enter để gửi" aria-label="Câu hỏi so sánh"></textarea>
          <button class="btn primary send" type="button" id="cSend">${icon("send")}<span>Gửi</span></button>
        </div>
        <div class="chips" id="cChips"><span class="lbl">Thử nhanh:</span></div>
      </div>
    </section>
  </div>`;

  for (const k of ["base", "steer"]) {
    const col = $(`[data-col="${k}"]`, root);
    COLS[k] = { body: $(".cmp-body", col), stat: $("[data-stat]", col), hist: [], vi: 0, n: 0 };
    resetCol(COLS[k]);
  }

  const sliders = [
    ["cScale", "scale", 1, (v) => "×" + (+v).toFixed(1)],
    ["cMax", "max", 1024, (v) => v + " token"],
    ["cTemp", "temp", 0, (v) => (+v === 0 ? "0 · ổn định" : (+v).toFixed(2))],
    ["cRep", "rep", 1.1, (v) => (+v).toFixed(2)],
  ];
  for (const [id, key, def, fmt] of sliders) {
    const s = $("#" + id, root);
    s.value = local.get("cmp." + key, def);
    const upd = () => {
      $(`#${id}Out`, root).textContent = fmt(s.value);
      local.set("cmp." + key, s.value);
      if (key === "scale") $("#cScaleChip", root).textContent = "×" + (+s.value).toFixed(1);
    };
    s.addEventListener("input", upd);
    upd();
  }
  const instr = $("#cInstr", root);
  instr.checked = local.get("cmp.instr", true);
  instr.onchange = () => local.set("cmp.instr", instr.checked);

  $("#cmpMode", root).addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) setMode(b.dataset.mode); });
  setMode(local.get("cmp.mode", "compare"));

  const input = $("#cInput", root);
  input.addEventListener("input", () => autosize(input, 160));
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
  $("#cSend", root).onclick = () => (busy ? stop() : send());
  $("#cNew", root).onclick = () => { if (!busy) Object.values(COLS).forEach(resetCol); };
  for (const q of EXAMPLES) {
    const b = h(`<button class="chip-btn" type="button"></button>`);
    b.textContent = q;
    b.onclick = () => send(q);
    $("#cChips", root).append(b);
  }
  on("status", (s) => showGemma(s.gemma));
}

export async function onShow() {
  try { showGemma((await getJSON("/api/status")).gemma); } catch {}
}

function showGemma(g) {
  const box = $("#gState", root);
  if (!box || !g) return;
  const map = {
    unavailable: `<span class="badge danger">${icon("alert")} Chưa cài PyTorch</span><br>${esc(g.error || "")}`,
    idle: `<span class="badge">Chưa nạp</span> Model sẽ tự nạp khi bạn gửi câu đầu tiên (lần đầu tải khoảng 540 MB).`,
    loading: `<span class="badge warn"><span class="spinner"></span> Đang nạp model…</span>`,
    ready: `<span class="badge accent">${icon("check")} Sẵn sàng</span> Chạy trên ${esc(g.device_name || "")} (${esc(g.dtype || "")}).`,
    error: `<span class="badge danger">${icon("alert")} Lỗi nạp model</span><br>${esc(g.error || "")}`,
  };
  box.innerHTML = map[g.state] || "";
}

function setMode(m) {
  local.set("cmp.mode", m);
  for (const b of $$("#cmpMode button", root)) b.setAttribute("aria-pressed", String(b.dataset.mode === m));
  $('[data-col="base"]', root).hidden = m === "steer";
  $('[data-col="steer"]', root).hidden = m === "base";
  $("#cmpCols", root).classList.toggle("single", m !== "compare");
  COLS.mode = m;
}

function resetCol(c) {
  c.hist = []; c.vi = 0; c.n = 0;
  c.stat.textContent = "VI 0/0";
  c.body.innerHTML = `<div class="empty-col"><b>Chưa có câu hỏi nào</b>Gõ câu hỏi bên dưới hoặc bấm một câu "Thử nhanh".</div>`;
}

function stop() {
  controller?.abort();
  stopAll();
}

function setBusy(b) {
  busy = b;
  const btn = $("#cSend", root);
  btn.className = b ? "btn danger send" : "btn primary send";
  btn.innerHTML = b ? `${icon("stop")}<span>Dừng</span>` : `${icon("send")}<span>Gửi</span>`;
  $("#cNew", root).disabled = b;
}

async function send(textArg) {
  if (busy) return;
  const input = $("#cInput", root);
  const text = (textArg ?? input.value).trim();
  if (!text) return input.focus();
  input.value = "";
  autosize(input, 160);
  const withInstr = $("#cInstr", root).checked;
  const content = withInstr ? `${text}\n${INSTR}` : text;
  const order = COLS.mode === "compare" ? ["base", "steer"] : [COLS.mode];
  const scale = +$("#cScale", root).value;
  const seed = Math.floor(Math.random() * 2 ** 31);
  const views = {};
  for (const k of order) {
    const c = COLS[k];
    c.body.querySelector(".empty-col")?.remove();
    c.hist.push({ role: "user", content });
    const u = h(`<div class="msg-u"></div>`);
    u.textContent = text;
    if (withInstr) { u.append(document.createElement("br"), h(`<span class="instr">+ ${INSTR}</span>`)); }
    const a = h(`<div class="msg-a md"><div class="waiting"><span class="typing"><i></i><i></i><i></i></span><span>${order.length > 1 && k !== order[0] ? "Đang chờ tới lượt…" : "Đang suy nghĩ…"}</span></div></div>`);
    const meta = h(`<div class="cmp-meta"></div>`);
    c.body.append(u, a, meta);
    c.body.scrollTop = c.body.scrollHeight;
    views[k] = { a, meta };
  }
  setBusy(true);
  controller = new AbortController();
  for (const k of order) {
    if (controller.signal.aborted) {
      views[k].a.innerHTML = `<p style="color:var(--muted)">Đã dừng trước khi trả lời.</p>`;
      COLS[k].hist.pop();
      continue;
    }
    await streamCol(k, views[k], k === "base" ? 0 : scale, seed);
  }
  setBusy(false);
  emit("status-refresh");
  input.focus();
}

async function streamCol(k, view, scale, seed) {
  const c = COLS[k];
  let text = "", info = null, failed = null, raf = 0, stopped = false;
  const paint = () => { raf = 0; if (text) { view.a.innerHTML = render(text); view.a.classList.add("streaming"); } c.body.scrollTop = c.body.scrollHeight; };
  const wait = view.a.querySelector(".waiting span:last-child");
  if (wait) wait.textContent = "Đang suy nghĩ…";
  try {
    await streamNDJSON("/api/chat", {
      model: GEMMA, system: "", messages: c.hist, options: {
        scale, seed, max_new_tokens: +$("#cMax", root).value, temperature: +$("#cTemp", root).value, repetition_penalty: +$("#cRep", root).value,
      },
    }, (o) => {
      if (o.status && wait) wait.textContent = o.status;
      if (o.t) { text += o.t; if (!raf) raf = requestAnimationFrame(paint); }
      if (o.error) failed = o.error;
      if (o.done) info = o;
    }, controller.signal);
  } catch (e) {
    if (e.name === "AbortError") stopped = true; else failed = e.message;
  }
  if (raf) cancelAnimationFrame(raf);
  view.a.classList.remove("streaming");
  view.a.innerHTML = text ? render(text) : `<p style="color:var(--muted)">${failed ? "Có lỗi xảy ra." : "(Không có câu trả lời)"}</p>`;
  const vi = isVi(text);
  c.n += 1;
  if (vi) c.vi += 1;
  c.stat.textContent = `VI ${c.vi}/${c.n}`;
  const parts = [];
  if (failed) parts.push(`<span class="lang stop">Lỗi: ${esc(failed)}</span>`);
  else if (stopped || info?.stopped) parts.push(`<span class="lang stop">Đã dừng</span>`);
  if (vi !== null && !failed) parts.push(`<span class="lang ${vi ? "vi" : "en"}">${vi ? "Tiếng Việt" : "Tiếng Anh"}</span>`);
  if (info?.tokens) parts.push(`<span>${info.tokens} token · ${info.tps} token/giây</span>`);
  view.meta.innerHTML = parts.join("");
  if (text) {
    const b = h(`<button class="btn ghost sm" type="button">${icon("copy")}Sao chép</button>`);
    b.onclick = () => copyText(text);
    view.meta.append(b);
    c.hist.push({ role: "assistant", content: text });
  } else {
    c.hist.pop();
  }
  c.body.scrollTop = c.body.scrollHeight;
}
