"""Lưu cài đặt và lịch sử trò chuyện thành file JSON trong thư mục data/."""
import json
import os
import re
import threading
import time
from pathlib import Path

ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")

DEFAULT_SETTINGS = {
    "system_prompt": (
        "Bạn là một trợ lý AI thân thiện và hữu ích. Hãy luôn trả lời bằng tiếng Việt có dấu, "
        "rõ ràng, có cấu trúc. Nếu không chắc chắn, hãy nói thật là bạn không biết."
    ),
    "temperature": 0.7,
    "num_ctx": 8192,
    "think": "auto",  # auto | on | off
    "ollama_url": "http://127.0.0.1:11434",
    "default_model": "",
    "font_size": "md",  # sm | md | lg
    "theme": "system",  # system | light | dark
}

_CHOICES = {
    "think": {"auto", "on", "off"},
    "font_size": {"sm", "md", "lg"},
    "theme": {"system", "light", "dark"},
}


def _atomic_write(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.conv_dir = root / "conversations"
        self.conv_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = root / "settings.json"
        self.lock = threading.Lock()

    # ---------- Cài đặt ----------
    def get_settings(self) -> dict:
        s = dict(DEFAULT_SETTINGS)
        try:
            saved = json.loads(self.settings_path.read_text(encoding="utf-8"))
            s.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS})
        except (OSError, ValueError):
            pass
        return s

    def put_settings(self, patch: dict) -> dict:
        with self.lock:
            s = self.get_settings()
            for k, v in (patch or {}).items():
                if k not in DEFAULT_SETTINGS:
                    continue
                if k in _CHOICES:
                    if v in _CHOICES[k]:
                        s[k] = v
                elif k == "temperature":
                    s[k] = max(0.0, min(2.0, float(v)))
                elif k == "num_ctx":
                    s[k] = int(max(1024, min(131072, int(v))))
                elif k == "ollama_url":
                    v = str(v).strip().rstrip("/")
                    if re.match(r"^https?://[A-Za-z0-9.\-\[\]:]+$", v):
                        s[k] = v
                else:
                    s[k] = str(v)[:8000]
            _atomic_write(self.settings_path, s)
            return s

    # ---------- Cuộc trò chuyện ----------
    def _conv_path(self, cid: str) -> Path:
        if not ID_RE.match(cid or ""):
            raise ValueError("id không hợp lệ")
        return self.conv_dir / f"{cid}.json"

    def list_convs(self) -> list:
        items = []
        for p in self.conv_dir.glob("*.json"):
            try:
                c = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            items.append({
                "id": c.get("id", p.stem),
                "title": c.get("title") or "Cuộc trò chuyện",
                "model": c.get("model", ""),
                "updated": c.get("updated", 0),
                "count": len(c.get("messages", [])),
            })
        items.sort(key=lambda x: x["updated"], reverse=True)
        return items

    def get_conv(self, cid: str):
        p = self._conv_path(cid)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))

    def put_conv(self, cid: str, data: dict) -> dict:
        p = self._conv_path(cid)
        msgs = []
        for m in data.get("messages", [])[:2000]:
            if m.get("role") not in ("user", "assistant"):
                continue
            item = {"role": m["role"], "content": str(m.get("content", ""))}
            if m.get("thinking"):
                item["thinking"] = str(m["thinking"])
            if isinstance(m.get("meta"), dict):
                item["meta"] = {k: m["meta"][k] for k in ("model", "tokens", "tps", "secs", "think_secs") if k in m["meta"]}
            msgs.append(item)
        now = time.time()
        old = self.get_conv(cid) or {}
        conv = {
            "id": cid,
            "title": str(data.get("title") or old.get("title") or "Cuộc trò chuyện")[:120],
            "model": str(data.get("model", ""))[:200],
            "created": old.get("created", now),
            "updated": now,
            "messages": msgs,
        }
        with self.lock:
            _atomic_write(p, conv)
        return conv

    def delete_conv(self, cid: str) -> None:
        p = self._conv_path(cid)
        if p.exists():
            p.unlink()

    def delete_all_convs(self) -> int:
        n = 0
        for p in self.conv_dir.glob("*.json"):
            p.unlink()
            n += 1
        return n
