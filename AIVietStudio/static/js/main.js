// Điều phối: tab, trạng thái máy chủ, giao diện sáng/tối, cỡ chữ.
import { $, $$, icon, getJSON, local, emit, on } from "./util.js";
import * as chat from "./chat.js";
import * as compare from "./compare.js";
import * as models from "./models.js";
import * as docs from "./docs.js";
import * as settings from "./settings.js";

const TABS = {
  chat: { label: "Trò chuyện", icon: "chat", mod: chat },
  compare: { label: "So sánh Gemma", icon: "compare", mod: compare },
  models: { label: "Mô hình", icon: "box", mod: models },
  docs: { label: "Tài liệu", icon: "book", mod: docs },
  settings: { label: "Cài đặt", icon: "gear", mod: settings },
};
const started = new Set();
export const state = { status: null, settings: null };

// ---------- Giao diện ----------
const sysDark = () => matchMedia("(prefers-color-scheme: dark)").matches;
function applyAppearance(s) {
  const root = document.documentElement;
  if (s.theme === "light" || s.theme === "dark") root.dataset.theme = s.theme;
  else delete root.dataset.theme;
  root.dataset.fs = s.font_size || "md";
  local.set("appearance", { theme: s.theme, font_size: s.font_size });
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : sysDark();
  $("#themeBtn").innerHTML = icon(dark ? "sun" : "moon");
}
on("settings-changed", (s) => { state.settings = s; applyAppearance(s); });
$("#themeBtn").onclick = () => {
  const root = document.documentElement;
  const dark = root.dataset.theme ? root.dataset.theme === "dark" : sysDark();
  settings.save({ theme: dark ? "light" : "dark" });
};

// ---------- Tab ----------
function show(name) {
  if (!TABS[name]) name = "chat";
  for (const b of $$(".tab")) b.setAttribute("aria-selected", String(b.dataset.tab === name));
  for (const k of Object.keys(TABS)) $(`#view-${k}`).hidden = k !== name;
  const t = TABS[name];
  if (!started.has(name)) { started.add(name); t.mod.init($(`#view-${name}`), state); }
  t.mod.onShow?.();
  if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
}
for (const b of $$(".tab")) {
  const t = TABS[b.dataset.tab];
  b.innerHTML = `${icon(t.icon)}<span>${t.label}</span>`;
  b.onclick = () => show(b.dataset.tab);
}
on("goto", (name) => show(name));
addEventListener("hashchange", () => show(location.hash.slice(1)));

// ---------- Trạng thái (Ollama, GPU) ----------
async function poll() {
  try {
    const s = await getJSON("/api/status");
    const prev = state.status;
    state.status = s;
    const ok = !!s.ollama.version;
    $("#pillOllama").innerHTML = `<span class="dot ${ok ? "ok" : "bad"}"></span>Ollama ${ok ? "đang chạy" : "chưa chạy"}`;
    const g = s.gpu || {};
    const pg = $("#pillGpu");
    if (g.state === "ok") { pg.hidden = false; pg.innerHTML = `${icon("chip")}${g.name.replace(/^NVIDIA (GeForce )?/, "")} · ${g.vram_gb} GB`; }
    else if (g.state === "none") { pg.hidden = false; pg.innerHTML = `${icon("chip")}Không có GPU NVIDIA`; }
    else pg.hidden = true;
    if (!prev || prev.ollama.version !== s.ollama.version || prev.gemma.state !== s.gemma.state) emit("status", s);
  } catch {
    $("#pillOllama").innerHTML = `<span class="dot bad"></span>Mất kết nối ứng dụng`;
  }
}

(async () => {
  try {
    state.settings = await getJSON("/api/settings");
    applyAppearance(state.settings);
  } catch {
    applyAppearance({});
  }
  await poll();
  setInterval(poll, 5000);
  on("status-refresh", poll);
  show(location.hash.slice(1) || "chat");
})();
