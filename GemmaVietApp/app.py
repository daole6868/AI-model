"""Gemma Việt: giao diện web chạy trên máy, so sánh Gemma-3-270M gốc và bản steer tiếng Việt.

Chạy:  python app.py            (tự mở trình duyệt ở http://127.0.0.1:7860)
       python app.py --cpu      (ép chạy CPU)
       python app.py --port 8000 --no-browser

Bản steer (Neeze/gemma-3-270m-it-vi-steer) = Gemma gốc + 1 vector 640 số cộng vào sau
post_feedforward_layernorm của tầng 16. Ứng dụng này tự gắn vector đó bằng một hook
(giống hệt file modeling_gemma3_vi.py của tác giả) nên KHÔNG cần trust_remote_code,
và có thể đổi độ mạnh (x0 = gốc, x1 = bản của tác giả) ngay lúc chạy.
"""
import argparse
import json
import mimetypes
import socket
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = "Neeze/gemma-3-270m-it-vi-steer"
REVISION = "61df599c465049993125ae41a6a4ebef864851f3"  # bản đã kiểm tra: chỉ khác Gemma gốc ở steer_bias
STEER_LAYER = 16
STATIC = Path(__file__).resolve().parent / "static"

mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("text/javascript", ".js")


def _console_utf8():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class Engine:
    """Giữ model, tokenizer và vector steer; mỗi lúc chỉ sinh một câu trả lời."""

    def __init__(self, force_cpu: bool = False):
        import torch
        from huggingface_hub import hf_hub_download
        from safetensors import safe_open
        from transformers import AutoTokenizer, Gemma3ForCausalLM
        from transformers.utils import logging as hf_logging

        hf_logging.set_verbosity_error()
        self.torch = torch

        if not force_cpu and torch.cuda.is_available():
            self.device, dtype = "cuda", torch.bfloat16
            self.device_name = torch.cuda.get_device_name(0)
        elif not force_cpu and getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            self.device, dtype = "mps", torch.float32
            self.device_name = "Apple GPU (MPS)"
        else:
            self.device, dtype = "cpu", torch.float32
            self.device_name = "CPU"
        self.dtype = str(dtype).replace("torch.", "")

        print(f"• Đang tải model {REPO} (lần đầu sẽ tải khoảng 540 MB)...", flush=True)
        self.tok = AutoTokenizer.from_pretrained(REPO, revision=REVISION)
        self.model = Gemma3ForCausalLM.from_pretrained(REPO, revision=REVISION, dtype=dtype)
        self.model.to(self.device).eval()

        weights = hf_hub_download(REPO, "model.safetensors", revision=REVISION)
        with safe_open(weights, framework="pt") as f:
            steer = f.get_tensor("steer_bias")
        self.steer = steer.float().to(self.device)
        self.steer_norm = float(self.steer.norm())

        self.scale = 0.0
        norm = self.model.model.layers[STEER_LAYER].post_feedforward_layernorm
        norm.register_forward_hook(self._add_steer)

        self.lock = threading.Lock()
        self.stop_event = threading.Event()

    def _add_steer(self, module, inputs, output):
        if self.scale == 0.0:
            return output
        return (output.float() + self.scale * self.steer).type_as(output)

    def info(self):
        return {
            "model": REPO,
            "revision": REVISION[:7],
            "device": self.device,
            "device_name": self.device_name,
            "dtype": self.dtype,
            "steer_layer": STEER_LAYER,
            "steer_size": int(self.steer.numel()),
            "steer_norm": round(self.steer_norm, 1),
        }

    def stream(self, messages, scale, max_new_tokens, temperature, repetition_penalty, seed):
        """Sinh câu trả lời, trả về từng mảnh chữ; phần tử cuối là dict thống kê."""
        torch = self.torch
        from transformers import StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer

        stop_event = threading.Event()

        class StopOnEvent(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return torch.full((input_ids.shape[0],), stop_event.is_set(),
                                  dtype=torch.bool, device=input_ids.device)

        with self.lock:
            self.stop_event = stop_event
            self.scale = float(scale)
            enc = self.tok.apply_chat_template(
                messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
            ).to(self.device)
            n_in = enc["input_ids"].shape[1]
            streamer = TextIteratorStreamer(self.tok, skip_prompt=True, skip_special_tokens=True)
            kwargs = dict(
                **enc,
                max_new_tokens=int(max_new_tokens),
                streamer=streamer,
                stopping_criteria=StoppingCriteriaList([StopOnEvent()]),
                repetition_penalty=float(repetition_penalty),
            )
            if temperature > 0:
                torch.manual_seed(int(seed))
                kwargs.update(do_sample=True, temperature=float(temperature), top_k=64, top_p=0.95)
            else:
                kwargs.update(do_sample=False, temperature=None, top_k=None, top_p=None)

            result = {}

            def run():
                try:
                    with torch.no_grad():
                        out = self.model.generate(**kwargs)
                    result["tokens"] = int(out.shape[1] - n_in)
                except Exception as e:  # báo lỗi lên giao diện thay vì treo
                    result["error"] = f"{type(e).__name__}: {e}"
                    streamer.end()

            t0 = time.time()
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            finished = False
            try:
                for piece in streamer:
                    if piece:
                        yield piece
                finished = True
            finally:
                if not finished:  # bên gọi ngừng đọc giữa chừng: dừng sinh chữ cho gọn
                    stop_event.set()
                worker.join()
            secs = time.time() - t0
            tokens = result.get("tokens", 0)
            yield {
                "done": True,
                "tokens": tokens,
                "secs": round(secs, 2),
                "tps": round(tokens / secs, 1) if secs > 0 else 0,
                "stopped": stop_event.is_set(),
                "error": result.get("error"),
            }

    def stop(self):
        self.stop_event.set()


def clamp(v, lo, hi, default):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def make_handler(engine: Engine):
    class Handler(BaseHTTPRequestHandler):
        server_version = "GemmaViet/1.0"

        def log_message(self, fmt, *args):  # giữ cửa sổ dòng lệnh gọn gàng
            pass

        def _json(self, obj, status=HTTPStatus.OK):
            body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _local_origin_ok(self):
            origin = self.headers.get("Origin")
            if not origin:
                return True
            host = self.headers.get("Host", "")
            return origin in (f"http://{host}",)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/api/info":
                return self._json(engine.info())
            if path in ("/", "/index.html"):
                path = "/index.html"
            target = (STATIC / path.lstrip("/")).resolve()
            if not target.is_file() or STATIC not in target.parents:
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            data = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/"):
                ctype += "; charset=utf-8"
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache" if target.suffix == ".html" else "max-age=86400")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not self._local_origin_ok():
                return self._json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
            if self.path == "/api/stop":
                engine.stop()
                return self._json({"ok": True})
            if self.path != "/api/chat":
                return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            try:
                length = int(self.headers.get("Content-Length", 0))
                req = json.loads(self.rfile.read(length) or b"{}")
                messages = [
                    {"role": m["role"], "content": str(m["content"])}
                    for m in req.get("messages", [])
                    if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()
                ]
                if not messages or messages[-1]["role"] != "user":
                    raise ValueError("cần ít nhất một câu hỏi của người dùng")
            except Exception as e:
                return self._json({"error": f"Yêu cầu không hợp lệ: {e}"}, HTTPStatus.BAD_REQUEST)

            params = dict(
                messages=messages,
                scale=clamp(req.get("scale"), -5, 5, 1.0),
                max_new_tokens=int(clamp(req.get("max_new_tokens"), 16, 4096, 1024)),
                temperature=clamp(req.get("temperature"), 0, 2, 0.0),
                repetition_penalty=clamp(req.get("repetition_penalty"), 1.0, 2.0, 1.0),
                seed=int(clamp(req.get("seed"), 0, 2**31 - 1, 0)),
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            gen = engine.stream(**params)
            try:
                for item in gen:
                    line = item if isinstance(item, dict) else {"t": item}
                    self.wfile.write((json.dumps(line, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                engine.stop()  # người dùng bấm Dừng hoặc đóng tab
                for _ in gen:
                    pass

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
    _console_utf8()
    ap = argparse.ArgumentParser(description="Gemma Việt: giao diện so sánh Gemma gốc và bản steer tiếng Việt")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7860)
    ap.add_argument("--cpu", action="store_true", help="ép chạy bằng CPU")
    ap.add_argument("--no-browser", action="store_true", help="không tự mở trình duyệt")
    args = ap.parse_args()

    engine = Engine(force_cpu=args.cpu)
    info = engine.info()
    print(f"• Thiết bị: {info['device_name']} ({info['dtype']})")
    print(f"• Vector steer: {info['steer_size']} số, gắn vào tầng {info['steer_layer']}")

    port = find_port(args.host, args.port)
    server = ThreadingHTTPServer((args.host, port), make_handler(engine))
    server.daemon_threads = True
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{port}"
    print(f"\n✅ Sẵn sàng! Mở trình duyệt tại: {url}")
    print("   (Giữ cửa sổ này mở trong lúc dùng. Nhấn Ctrl+C để tắt.)\n", flush=True)
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
