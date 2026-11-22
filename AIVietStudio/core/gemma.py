"""Gemma-3-270M + vector tiếng Việt (Neeze/gemma-3-270m-it-vi-steer), chạy bằng PyTorch.

Model chỉ được nạp khi cần (lần đầu dùng tab So sánh hoặc chọn model này để chat).
"""
import importlib.util
import threading
import time

GEMMA_ID = "gemma-vi-steer"
REPO = "Neeze/gemma-3-270m-it-vi-steer"
REVISION = "61df599c465049993125ae41a6a4ebef864851f3"  # đã kiểm tra: chỉ khác Gemma gốc ở steer_bias
STEER_LAYER = 16


class _Engine:
    def __init__(self, force_cpu: bool):
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

        self.tok = AutoTokenizer.from_pretrained(REPO, revision=REVISION)
        self.model = Gemma3ForCausalLM.from_pretrained(REPO, revision=REVISION, dtype=dtype)
        self.model.to(self.device).eval()
        weights = hf_hub_download(REPO, "model.safetensors", revision=REVISION)
        with safe_open(weights, framework="pt") as f:
            self.steer = f.get_tensor("steer_bias").float().to(self.device)
        self.scale = 0.0
        self.model.model.layers[STEER_LAYER].post_feedforward_layernorm.register_forward_hook(self._hook)
        self.lock = threading.Lock()

    def _hook(self, module, inputs, output):
        # Giống hệt modeling_gemma3_vi.py của tác giả khi scale = 1.
        if self.scale == 0.0:
            return output
        return (output.float() + self.scale * self.steer).type_as(output)

    def stream(self, messages, scale, max_new_tokens, temperature, repetition_penalty, seed, stop_event):
        torch = self.torch
        from transformers import StoppingCriteria, StoppingCriteriaList, TextIteratorStreamer

        class StopOnEvent(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return torch.full((input_ids.shape[0],), stop_event.is_set(),
                                  dtype=torch.bool, device=input_ids.device)

        with self.lock:
            self.scale = float(scale)
            enc = self.tok.apply_chat_template(
                messages, add_generation_prompt=True, return_tensors="pt", return_dict=True
            ).to(self.device)
            n_in = enc["input_ids"].shape[1]
            streamer = TextIteratorStreamer(self.tok, skip_prompt=True, skip_special_tokens=True)
            kwargs = dict(**enc, max_new_tokens=int(max_new_tokens), streamer=streamer,
                          stopping_criteria=StoppingCriteriaList([StopOnEvent()]),
                          repetition_penalty=float(repetition_penalty))
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
                except Exception as e:
                    result["error"] = f"{type(e).__name__}: {e}"
                    streamer.end()

            t0 = time.time()
            worker = threading.Thread(target=run, daemon=True)
            worker.start()
            finished = False
            try:
                for piece in streamer:
                    if piece:
                        yield {"t": piece}
                finished = True
            finally:
                if not finished:
                    stop_event.set()
                worker.join()
            secs = time.time() - t0
            tokens = result.get("tokens", 0)
            if result.get("error"):
                yield {"error": result["error"]}
            yield {"done": True, "tokens": tokens, "secs": round(secs, 2),
                   "tps": round(tokens / secs, 1) if secs > 0 else 0, "stopped": stop_event.is_set()}


class GemmaManager:
    def __init__(self, force_cpu: bool = False):
        self.force_cpu = force_cpu
        self.engine = None
        self.state = "idle"  # idle | loading | ready | error | unavailable
        self.error = None
        self._lock = threading.Lock()
        self._loaded = threading.Event()
        if importlib.util.find_spec("torch") is None or importlib.util.find_spec("transformers") is None:
            self.state = "unavailable"
            self.error = "Chưa cài PyTorch/Transformers (chạy lại file cài đặt)."

    def status(self) -> dict:
        s = {"id": GEMMA_ID, "repo": REPO, "state": self.state, "error": self.error}
        if self.engine:
            s.update(device=self.engine.device, device_name=self.engine.device_name, dtype=self.engine.dtype)
        return s

    def _load(self):
        try:
            self.engine = _Engine(self.force_cpu)
            self.state, self.error = "ready", None
        except Exception as e:
            self.state, self.error = "error", f"{type(e).__name__}: {e}"
        finally:
            self._loaded.set()

    def load_async(self):
        with self._lock:
            if self.state in ("idle", "error"):
                self.state, self.error = "loading", None
                self._loaded.clear()
                threading.Thread(target=self._load, daemon=True).start()
        return self.status()

    def stream(self, messages, opts, stop_event):
        if self.state == "unavailable":
            yield {"error": self.error}
            return
        if self.state != "ready":
            yield {"status": "Đang nạp model Gemma (lần đầu sẽ tải khoảng 540 MB)…"}
            self.load_async()
            while not self._loaded.wait(0.5):
                if stop_event.is_set():
                    yield {"done": True, "tokens": 0, "stopped": True}
                    return
            if self.state != "ready":
                yield {"error": self.error or "Không nạp được model Gemma."}
                return
        yield from self.engine.stream(
            messages,
            scale=float(opts.get("scale", 1.0)),
            max_new_tokens=int(opts.get("max_new_tokens", 1024)),
            temperature=float(opts.get("temperature", 0.0)),
            repetition_penalty=float(opts.get("repetition_penalty", 1.1)),
            seed=int(opts.get("seed", 0)),
            stop_event=stop_event,
        )
