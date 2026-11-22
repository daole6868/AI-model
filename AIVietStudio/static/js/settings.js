// Tab Cài đặt: lời nhắc hệ thống, độ sáng tạo, ngữ cảnh, suy nghĩ, giao diện, kết nối, dữ liệu.
import { $, $$, esc, icon, getJSON, sendJSON, toast, emit, on } from "./util.js";
import { state } from "./main.js";

const DEFAULT_PROMPT = "Bạn là một trợ lý AI thân thiện và hữu ích. Hãy luôn trả lời bằng tiếng Việt có dấu, rõ ràng, có cấu trúc. Nếu không chắc chắn, hãy nói thật là bạn không biết.";
let root;
let timer = null;
let pending = {};

// Lưu cài đặt (gộp các thay đổi liên tiếp rồi mới gửi lên máy chủ).
export function save(patch, quiet = false) {
  Object.assign(pending, patch);
  state.settings = { ...(state.settings || {}), ...patch };
  emit("settings-changed", state.settings);
  clearTimeout(timer);
  timer = setTimeout(async () => {
    const p = pending;
    pending = {};
    try {
      state.settings = await sendJSON("/api/settings", "PUT", p);
      if (!quiet) flashSaved();
    } catch (e) {
      toast("Không lưu được cài đặt: " + e.message);
    }
  }, 350);
}

function flashSaved() {
  const n = $("#savedNote", root || document);
  if (!n) return;
  n.classList.add("show");
  clearTimeout(flashSaved.t);
  flashSaved.t = setTimeout(() => n.classList.remove("show"), 1400);
}

function seg(name, options, value) {
  return `<div class="segmented" data-seg="${name}" role="group">${options.map(([v, label]) =>
    `<button type="button" data-v="${v}" aria-pressed="${v === value}">${label}</button>`).join("")}</div>`;
}

export function init(el) {
  root = el;
  draw();
  on("settings-changed", (s) => {
    for (const g of $$("[data-seg]", root)) {
      for (const b of $$("button", g)) b.setAttribute("aria-pressed", String(b.dataset.v === String(s[g.dataset.seg])));
    }
  });
}

export function onShow() {
  checkOllama(true);
}

function draw() {
  const s = state.settings || {};
  root.innerHTML = `
  <div class="page-inner settings-wrap">
    <div class="page-head" style="display:flex;align-items:flex-end;gap:1rem">
      <div style="flex:1"><h1>Cài đặt</h1><p>Mọi thay đổi được lưu tự động.</p></div>
      <span class="saved-note" id="savedNote">${icon("check")} Đã lưu</span>
    </div>

    <section class="card set-card">
      <h2>Trợ lý AI</h2>
      <div class="set-row stack">
        <label for="sysPrompt"><b>Lời nhắc hệ thống</b><span>Hướng dẫn chung AI luôn làm theo trong mọi cuộc trò chuyện (giọng điệu, ngôn ngữ, vai trò…).</span></label>
        <textarea class="field" id="sysPrompt"></textarea>
        <div><button class="btn sm" type="button" id="resetPrompt">${icon("refresh")}Khôi phục mặc định</button></div>
      </div>
      <div class="set-row">
        <label for="temp"><b>Độ sáng tạo</b><span>Thấp: chính xác, ổn định. Cao: đa dạng, bay bổng hơn.</span></label>
        <div class="group"><div class="group-label"><span></span><output id="tempOut"></output></div>
          <input type="range" id="temp" min="0" max="1.5" step="0.05"></div>
      </div>
      <div class="set-row">
        <label for="ctx"><b>Độ dài ngữ cảnh</b><span>AI nhớ được bao nhiêu chữ trong một cuộc trò chuyện. Cao hơn thì tốn bộ nhớ GPU hơn.</span></label>
        <select id="ctx">
          <option value="2048">2.048 token (ít bộ nhớ)</option>
          <option value="4096">4.096 token</option>
          <option value="8192">8.192 token (khuyên dùng)</option>
          <option value="16384">16.384 token</option>
          <option value="32768">32.768 token (cần nhiều VRAM)</option>
        </select>
      </div>
      <div class="set-row">
        <label><b>Chế độ suy nghĩ</b><span>Với model biết suy nghĩ trước khi trả lời (như Qwen3). Tắt để trả lời nhanh hơn.</span></label>
        ${seg("think", [["auto", "Tự động"], ["on", "Bật"], ["off", "Tắt"]], s.think)}
      </div>
    </section>

    <section class="card set-card">
      <h2>Giao diện</h2>
      <div class="set-row">
        <label><b>Chủ đề màu</b><span>Sáng, tối, hoặc theo cài đặt của Windows.</span></label>
        ${seg("theme", [["system", "Theo hệ thống"], ["light", "Sáng"], ["dark", "Tối"]], s.theme)}
      </div>
      <div class="set-row">
        <label><b>Cỡ chữ</b><span>Phóng to toàn bộ chữ trong ứng dụng cho dễ đọc.</span></label>
        ${seg("font_size", [["sm", "Nhỏ"], ["md", "Vừa"], ["lg", "Lớn"]], s.font_size)}
      </div>
    </section>

    <section class="card set-card">
      <h2>Kết nối Ollama</h2>
      <div class="set-row">
        <label for="ollamaUrl"><b>Địa chỉ Ollama</b><span>Thường không cần đổi. Mặc định: http://127.0.0.1:11434</span></label>
        <div class="ctl"><input type="url" id="ollamaUrl" spellcheck="false"><button class="btn" type="button" id="checkOllama">Kiểm tra</button></div>
      </div>
      <div class="set-row stack"><div class="hint" id="ollamaCheck"></div></div>
    </section>

    <section class="card set-card">
      <h2>Dữ liệu</h2>
      <div class="set-row">
        <label><b>Lịch sử trò chuyện</b><span>Lưu trong thư mục <code>data/conversations</code> cạnh ứng dụng, không gửi đi đâu.</span></label>
        <div><button class="btn danger" type="button" id="clearConvs">${icon("trash")}Xóa toàn bộ lịch sử</button></div>
      </div>
    </section>

    <section class="card set-card">
      <h2>Giới thiệu</h2>
      <div class="set-row stack"><p class="hint" style="font-size:.88rem">
        <b>AI Việt Studio</b>: trò chuyện với AI chạy trên máy (qua Ollama), so sánh Gemma-3-270M với bản "nghe lời tiếng Việt",
        tải model và bộ tài liệu đọc offline. Font chữ: Be Vietnam Pro (SIL Open Font License).
        Các model tải về tuân theo giấy phép riêng của từng nhà phát triển.</p></div>
    </section>
  </div>`;

  const sp = $("#sysPrompt", root);
  sp.value = s.system_prompt ?? DEFAULT_PROMPT;
  sp.addEventListener("input", () => save({ system_prompt: sp.value }));
  $("#resetPrompt", root).onclick = () => { sp.value = DEFAULT_PROMPT; save({ system_prompt: DEFAULT_PROMPT }); };

  const t = $("#temp", root);
  t.value = s.temperature ?? 0.7;
  const showT = () => ($("#tempOut", root).textContent = (+t.value).toFixed(2));
  showT();
  t.addEventListener("input", () => { showT(); save({ temperature: +t.value }); });

  const ctx = $("#ctx", root);
  ctx.value = String(s.num_ctx ?? 8192);
  if (!ctx.value) { ctx.append(new Option(`${s.num_ctx} token`, String(s.num_ctx))); ctx.value = String(s.num_ctx); }
  ctx.onchange = () => save({ num_ctx: +ctx.value });

  for (const g of $$("[data-seg]", root)) {
    g.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (b) save({ [g.dataset.seg]: b.dataset.v });
    });
  }

  const url = $("#ollamaUrl", root);
  url.value = s.ollama_url || "http://127.0.0.1:11434";
  url.addEventListener("change", () => { save({ ollama_url: url.value.trim() }); setTimeout(() => checkOllama(), 600); });
  $("#checkOllama", root).onclick = () => checkOllama();

  $("#clearConvs", root).onclick = async () => {
    if (!confirm("Xóa TOÀN BỘ lịch sử trò chuyện? Không thể hoàn tác.")) return;
    try {
      const r = await sendJSON("/api/convs", "DELETE");
      emit("convs-cleared");
      toast(`Đã xóa ${r.deleted} cuộc trò chuyện`);
    } catch (e) { toast(e.message); }
  };
}

async function checkOllama(silent) {
  const box = $("#ollamaCheck", root);
  if (!box) return;
  if (!silent) box.innerHTML = `<span style="display:inline-flex;gap:.5rem;align-items:center"><span class="spinner"></span>Đang kiểm tra…</span>`;
  try {
    const st = await getJSON("/api/status");
    box.innerHTML = st.ollama.version
      ? `<span class="badge accent">${icon("check")} Kết nối được</span> Ollama phiên bản ${esc(st.ollama.version)} tại ${esc(st.ollama.url)}`
      : `<span class="badge danger">${icon("alert")} Không kết nối được</span> Hãy mở ứng dụng Ollama, hoặc kiểm tra lại địa chỉ.`;
  } catch {
    box.textContent = "Không kiểm tra được.";
  }
}
