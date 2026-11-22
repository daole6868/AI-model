"""AI Việt Studio: trò chuyện với AI chạy trên máy, so sánh Gemma tiếng Việt, tải model và tài liệu.

Chạy:  python app.py               (tự mở trình duyệt ở http://127.0.0.1:7860)
       python app.py --cpu         (ép Gemma chạy bằng CPU)
       python app.py --port 8000 --no-browser
"""
import argparse
import json
import mimetypes
import re
import secrets
import socket
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

APP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(APP_DIR))

from core.docs import Docs  # noqa: E402
from core.gemma import GEMMA_ID, GemmaManager  # noqa: E402
from core.ollama import Ollama, OllamaError  # noqa: E402
from core.store import Store  # noqa: E402

VERSION = "1.0"
STATIC = APP_DIR / "static"
DATA = APP_DIR / "data"

mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/webp", ".webp")


class App:
    def __init__(self, force_cpu: bool):
        self.store = Store(DATA)
        self.ollama = Ollama(lambda: self.store.get_settings()["ollama_url"])
        self.gemma = GemmaManager(force_cpu=force_cpu)
        self.docs = Docs(DATA, APP_DIR / "docs_bundled")
        self.active = set()  # các yêu cầu đang sinh chữ (để nút Dừng hoạt động)
        self.active_lock = threading.Lock()
        self.gpu = {"state": "checking"}
        threading.Thread(target=self._detect_gpu, daemon=True).start()

    def _detect_gpu(self):
        try:
            import torch
            if torch.cuda.is_available():
                p = torch.cuda.get_device_properties(0)
                self.gpu = {"state": "ok", "name": p.name, "vram_gb": round(p.total_memory / 2**30, 1)}
            else:
                self.gpu = {"state": "none"}
        except Exception:
            self.gpu = {"state": "unknown"}

    def stop_all(self):
        with self.active_lock:
            for ev in self.active:
                ev.set()

    def tracked(self, gen_factory):
        ev = threading.Event()
        with self.active_lock:
            self.active.add(ev)
        try:
            yield from gen_factory(ev)
        finally:
            with self.active_lock:
                self.active.discard(ev)


def clean_messages(raw) -> list:
    msgs = []
    for m in raw or []:
        role = m.get("role")
        content = str(m.get("content", ""))
        if role in ("user", "assistant") and content.strip():
            msgs.append({"role": role, "content": content})
    if not msgs or msgs[-1]["role"] != "user":
        raise ValueError("cần ít nhất một câu hỏi của người dùng")
    return msgs


def num(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = f"AIVietStudio/{VERSION}"
        protocol_version = "HTTP/1.0"

        def log_message(self, fmt, *args):
            pass

        # ---------- tiện ích ----------
        def send_json(self, obj, status=HTTPStatus.OK):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_file(self, path: Path, cache=True):
            data = path.read_bytes()
            ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/json",):
                ctype += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "max-age=3600" if cache else "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def stream(self, gen):
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            try:
                for obj in gen:
                    self.wfile.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass
            except Exception as e:  # lỗi giữa chừng: báo về giao diện
                try:
                    self.wfile.write((json.dumps({"error": str(e), "done": True}, ensure_ascii=False) + "\n").encode())
                except Exception:
                    pass
            finally:
                gen.close()

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 20_000_000:
                raise ValueError("dữ liệu quá lớn")
            return json.loads(self.rfile.read(n) or b"{}")

        def same_origin(self):
            origin = self.headers.get("Origin")
            return not origin or origin == f"http://{self.headers.get('Host', '')}"

        # ---------- GET ----------
        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            try:
                if path == "/api/status":
                    return self.send_json({
                        "version": VERSION,
                        "ollama": {"version": app.ollama.version(), "url": app.store.get_settings()["ollama_url"]},
                        "gemma": app.gemma.status(),
                        "gpu": app.gpu,
                    })
                if path == "/api/models":
                    try:
                        models, err = app.ollama.models(), None
                    except OllamaError as e:
                        models, err = [], str(e)
                    return self.send_json({"ollama": models, "ollama_error": err, "gemma": app.gemma.status()})
                if path == "/api/settings":
                    return self.send_json(app.store.get_settings())
                if path == "/api/convs":
                    return self.send_json(app.store.list_convs())
                m = re.match(r"^/api/convs/([A-Za-z0-9_-]+)$", path)
                if m:
                    c = app.store.get_conv(m.group(1))
                    return self.send_json(c) if c else self.send_json({"error": "không tìm thấy"}, HTTPStatus.NOT_FOUND)
                if path == "/api/docs":
                    return self.send_json(app.docs.catalog())
                if path == "/api/docs/export.zip":
                    data = app.docs.export_zip()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", 'attachment; filename="Bo-tai-lieu-AI-Viet.zip"')
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                m = re.match(r"^/api/docs/([a-z0-9-]+)$", path)
                if m:
                    d = app.docs.read(m.group(1))
                    return self.send_json(d) if d else self.send_json({"error": "không tìm thấy"}, HTTPStatus.NOT_FOUND)
                m = re.match(r"^/docs-assets/([a-z0-9-]+)/([^/]+)$", path)
                if m:
                    p = app.docs.asset_path(m.group(1), m.group(2))
                    return self.send_file(p) if p else self.send_json({"error": "không tìm thấy"}, HTTPStatus.NOT_FOUND)
                # file tĩnh của giao diện
                rel = "index.html" if path in ("/", "/index.html") else path.lstrip("/")
                target = (STATIC / rel).resolve()
                if target.is_file() and STATIC in target.parents:
                    return self.send_file(target, cache=not target.suffix in (".html", ".js", ".css"))
                return self.send_json({"error": "không tìm thấy"}, HTTPStatus.NOT_FOUND)
            except (BrokenPipeError, ConnectionResetError):
                pass

        # ---------- POST / PUT / DELETE ----------
        def do_POST(self):
            self._mutate("POST")

        def do_PUT(self):
            self._mutate("PUT")

        def do_DELETE(self):
            self._mutate("DELETE")

        def _mutate(self, method):
            if not self.same_origin():
                return self.send_json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
            path = urlsplit(self.path).path
            try:
                req = self.body() if method in ("POST", "PUT") else {}
            except Exception as e:
                return self.send_json({"error": f"Yêu cầu không hợp lệ: {e}"}, HTTPStatus.BAD_REQUEST)
            try:
                if method == "POST" and path == "/api/chat":
                    return self.chat(req)
                if method == "POST" and path == "/api/stop":
                    app.stop_all()
                    return self.send_json({"ok": True})
                if method == "POST" and path == "/api/models/pull":
                    name = str(req.get("name", "")).strip()
                    if not re.match(r"^[A-Za-z0-9._:/-]{1,120}$", name):
                        return self.send_json({"error": "Tên model không hợp lệ"}, HTTPStatus.BAD_REQUEST)
                    return self.stream(app.tracked(lambda ev: app.ollama.pull(name, ev)))
                if method == "POST" and path == "/api/models/delete":
                    app.ollama.delete(str(req.get("name", "")))
                    return self.send_json({"ok": True})
                if method == "POST" and path == "/api/gemma/load":
                    return self.send_json(app.gemma.load_async())
                if method == "PUT" and path == "/api/settings":
                    return self.send_json(app.store.put_settings(req))
                if method == "POST" and path == "/api/convs":
                    cid = secrets.token_urlsafe(9).replace("-", "a").replace("_", "b")
                    return self.send_json(app.store.put_conv(cid, req))
                m = re.match(r"^/api/convs/([A-Za-z0-9_-]+)$", path)
                if m and method == "PUT":
                    return self.send_json(app.store.put_conv(m.group(1), req))
                if m and method == "DELETE":
                    app.store.delete_conv(m.group(1))
                    return self.send_json({"ok": True})
                if method == "DELETE" and path == "/api/convs":
                    return self.send_json({"deleted": app.store.delete_all_convs()})
                if method == "POST" and path == "/api/docs/download":
                    ids = req.get("ids") or [d["id"] for d in app.docs.catalog() if not d["downloaded"]]
                    return self.stream(x for x in app.docs.download_many(ids))
                return self.send_json({"error": "không tìm thấy"}, HTTPStatus.NOT_FOUND)
            except OllamaError as e:
                return self.send_json({"error": str(e)}, HTTPStatus.BAD_GATEWAY)
            except ValueError as e:
                return self.send_json({"error": str(e)}, HTTPStatus.BAD_REQUEST)

        def chat(self, req):
            messages = clean_messages(req.get("messages"))
            model = str(req.get("model", ""))
            opts = req.get("options") or {}
            s = app.store.get_settings()
            system = req.get("system", s["system_prompt"])
            if system:
                messages = [{"role": "system", "content": str(system)}] + messages
            if model == GEMMA_ID:
                gopts = {
                    "scale": num(opts.get("scale"), -5, 5, 1.0),
                    "max_new_tokens": int(num(opts.get("max_new_tokens"), 16, 4096, 1024)),
                    "temperature": num(opts.get("temperature"), 0, 2, 0.0),
                    "repetition_penalty": num(opts.get("repetition_penalty"), 1, 2, 1.1),
                    "seed": int(num(opts.get("seed"), 0, 2**31 - 1, 0)),
                }
                return self.stream(app.tracked(lambda ev: app.gemma.stream(messages, gopts, ev)))
            if not model:
                raise ValueError("Chưa chọn model")

            def run(ev):
                try:
                    yield from app.ollama.chat(
                        model, messages,
                        temperature=num(opts.get("temperature", s["temperature"]), 0, 2, 0.7),
                        num_ctx=int(num(opts.get("num_ctx", s["num_ctx"]), 1024, 131072, 8192)),
                        think=opts.get("think", s["think"]),
                        stop_event=ev,
                    )
                except OllamaError as e:
                    yield {"error": str(e)}
                    yield {"done": True, "tokens": 0}
            return self.stream(app.tracked(run))

    return Handler


def find_port(host: str, start: int) -> int:
    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    raise SystemExit(f"Không tìm được cổng trống từ {start} đến {start + 19}.")


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="AI Việt Studio")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--cpu", action="store_true", help="ép Gemma chạy bằng CPU")
    ap.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    args = ap.parse_args()

    app = App(force_cpu=args.cpu)
    ver = app.ollama.version()
    print("=" * 56)
    print("  AI VIỆT STUDIO")
    print("=" * 56)
    print(f"• Ollama: {'đang chạy (bản ' + ver + ')' if ver else 'CHƯA chạy (xem tab Mô hình trong ứng dụng)'}")
    print(f"• Gemma tiếng Việt: {'sẵn sàng nạp khi cần' if app.gemma.state != 'unavailable' else app.gemma.error}")

    port = find_port(args.host, args.port)
    server = ThreadingHTTPServer((args.host, port), make_handler(app))
    server.daemon_threads = True
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{port}"
    print(f"\n✅ Sẵn sàng! Mở trình duyệt tại: {url}")
    print("   Giữ cửa sổ này mở trong lúc dùng. Nhấn Ctrl+C để tắt.\n", flush=True)
    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nĐã tắt. Hẹn gặp lại!")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
