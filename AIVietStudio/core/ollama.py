"""Nói chuyện với Ollama (http://127.0.0.1:11434) để chạy các model lớn trên GPU."""
import json
import time
import urllib.error
import urllib.request

# Ollama chạy trên chính máy này: bỏ qua mọi proxy hệ thống.
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class OllamaError(Exception):
    pass


class ThinkSplitter:
    """Tách phần <think>...</think> (nếu model viết lẫn vào nội dung) thành 'th' và phần trả lời 't'."""

    def __init__(self):
        self.buf = ""
        self.in_think = False

    def feed(self, s: str):
        self.buf += s
        out = []
        while self.buf:
            tag = "</think>" if self.in_think else "<think>"
            i = self.buf.find(tag)
            kind = "th" if self.in_think else "t"
            if i >= 0:
                if i:
                    out.append((kind, self.buf[:i]))
                self.buf = self.buf[i + len(tag):]
                self.in_think = not self.in_think
                continue
            keep = 0  # giữ lại phần có thể là đầu của thẻ, chờ chữ tiếp theo
            for k in range(min(len(tag) - 1, len(self.buf)), 0, -1):
                if tag.startswith(self.buf[-k:]):
                    keep = k
                    break
            emit = self.buf[: len(self.buf) - keep]
            if emit:
                out.append((kind, emit))
            self.buf = self.buf[len(self.buf) - keep:]
            break
        return out

    def flush(self):
        out = [("th" if self.in_think else "t", self.buf)] if self.buf else []
        self.buf = ""
        return out


class Ollama:
    def __init__(self, get_url):
        self.get_url = get_url

    def _open(self, method, path, body=None, timeout=10):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(
            self.get_url().rstrip("/") + path, data=data, method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            return _opener.open(req, timeout=timeout)
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read().decode("utf-8", "replace")).get("error") or str(e)
            except Exception:
                msg = str(e)
            raise OllamaError(msg) from None
        except (urllib.error.URLError, OSError) as e:
            raise OllamaError(f"Không kết nối được Ollama ({getattr(e, 'reason', e)})") from None

    def version(self):
        try:
            with self._open("GET", "/api/version", timeout=2) as r:
                return json.load(r).get("version")
        except Exception:
            return None

    def models(self) -> list:
        with self._open("GET", "/api/tags", timeout=5) as r:
            raw = json.load(r).get("models", [])
        out = []
        for m in raw:
            d = m.get("details") or {}
            out.append({
                "name": m.get("name") or m.get("model"),
                "size": m.get("size", 0),
                "modified": m.get("modified_at", ""),
                "family": d.get("family", ""),
                "params": d.get("parameter_size", ""),
                "quant": d.get("quantization_level", ""),
            })
        out.sort(key=lambda x: x["name"] or "")
        return out

    def delete(self, name: str) -> None:
        self._open("DELETE", "/api/delete", {"model": name}).close()

    def pull(self, name: str, stop_event):
        """Tải model; trả về từng dòng tiến độ đã chuẩn hóa."""
        resp = self._open("POST", "/api/pull", {"model": name, "stream": True}, timeout=120)
        try:
            for line in resp:
                if stop_event.is_set():
                    break
                if not line.strip():
                    continue
                o = json.loads(line)
                if o.get("error"):
                    yield {"error": o["error"]}
                    return
                yield {k: o[k] for k in ("status", "digest", "total", "completed") if k in o}
        finally:
            resp.close()

    def chat(self, model, messages, temperature, num_ctx, think, stop_event):
        """Trò chuyện; trả về {'t': chữ}, {'th': suy nghĩ} và cuối cùng {'done': ...}."""
        body = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {"temperature": float(temperature), "num_ctx": int(num_ctx)},
        }
        if think in ("on", "off"):
            body["think"] = think == "on"
        t0 = time.time()
        try:
            resp = self._open("POST", "/api/chat", body, timeout=900)
        except OllamaError as e:
            if "think" in body and "think" in str(e).lower():
                body.pop("think")  # model không hỗ trợ chế độ suy nghĩ: thử lại không có nó
                resp = self._open("POST", "/api/chat", body, timeout=900)
            else:
                raise
        splitter = ThinkSplitter()
        final = {}
        try:
            for line in resp:
                if stop_event.is_set():
                    break
                if not line.strip():
                    continue
                o = json.loads(line)
                if o.get("error"):
                    raise OllamaError(o["error"])
                msg = o.get("message") or {}
                if msg.get("thinking"):
                    yield {"th": msg["thinking"]}
                if msg.get("content"):
                    for kind, text in splitter.feed(msg["content"]):
                        yield {kind: text}
                if o.get("done"):
                    final = o
                    break
            for kind, text in splitter.flush():
                yield {kind: text}
        finally:
            resp.close()
        tokens = int(final.get("eval_count") or 0)
        eval_s = (final.get("eval_duration") or 0) / 1e9
        yield {
            "done": True,
            "tokens": tokens,
            "tps": round(tokens / eval_s, 1) if eval_s > 0 else 0,
            "secs": round(time.time() - t0, 2),
            "stopped": stop_event.is_set(),
        }
