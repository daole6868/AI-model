"""Bộ tài liệu: tải các bài viết gốc về máy (kèm hình) để đọc offline, và đóng gói thành .zip."""
import io
import json
import re
import shutil
import time
import urllib.request
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

RAW = "https://raw.githubusercontent.com"
UA = {"User-Agent": "AIVietStudio/1.0 (local desktop app)"}
ID_RE = re.compile(r"^[a-z0-9-]{2,64}$")
ASSET_RE = re.compile(r"^[A-Za-z0-9._-]{1,120}$")

CATALOG = [
    {
        "id": "tom-tat", "kind": "bundled", "file": "tom-tat.md",
        "title": "Tóm tắt & đánh giá: chuyển hành vi LFM3-1.7B sang Gemma-3-270M",
        "author": "AI Việt Studio", "group": "Bắt đầu từ đây",
        "summary": "Đọc nhanh 4 nguồn trong bài chia sẻ, những gì đã kiểm chứng và những chỗ bị nói quá.",
    },
    {
        "id": "huong-dan", "kind": "bundled", "file": "huong-dan.md",
        "title": "Hướng dẫn sử dụng AI Việt Studio",
        "author": "AI Việt Studio", "group": "Bắt đầu từ đây",
        "summary": "Cài đặt, tải model, trò chuyện, so sánh và xử lý lỗi thường gặp.",
    },
    {
        "id": "neeze-lfm3-gemma", "kind": "mdx",
        "url": f"{RAW}/Neeze/docs/main/src/content/docs/practical-ai/weight-programming-lfm3-to-gemma.mdx",
        "page": "https://neeze.github.io/docs/practical-ai/weight-programming-lfm3-to-gemma/",
        "title": "Đem hành vi từ model lớn xuống model nhỏ hơn 6 lần mà không cần train",
        "author": "Neeze (Nam Nam)", "group": "Bài viết gốc",
        "summary": "Bài blog gốc: dò \"mạch thói quen\" ở LFM3-1.7B rồi cấy 640 con số vào Gemma-3-270M.",
    },
    {
        "id": "model-card", "kind": "hf",
        "url": "https://huggingface.co/Neeze/gemma-3-270m-it-vi-steer/raw/main/README.md",
        "code": "https://huggingface.co/Neeze/gemma-3-270m-it-vi-steer/raw/main/modeling_gemma3_vi.py",
        "page": "https://huggingface.co/Neeze/gemma-3-270m-it-vi-steer",
        "title": "Model card: Neeze/gemma-3-270m-it-vi-steer",
        "author": "Neeze · Hugging Face", "group": "Bài viết gốc",
        "summary": "Trang giới thiệu model trên Hugging Face, kèm file code gắn vector 640 số.",
    },
    {
        "id": "mit-wsp", "kind": "html",
        "url": f"{RAW}/rikiyat/rikiyat.github.io/master/blog/weight-space-programming/index.html",
        "page": "https://rikiyat.github.io/blog/weight-space-programming/",
        "title": "Sparks of Weight-Space Programming",
        "author": "Rikiya Takehi và cộng sự · MIT CSAIL", "group": "Bài viết gốc",
        "summary": "LLM đọc và sửa trực tiếp weight của mạng nơ-ron (tiếng Anh).",
    },
    {
        "id": "neuron-explorer", "kind": "md",
        "url": f"{RAW}/lyramakesmusic/neuron-explorer/main/README.md",
        "page": "https://github.com/lyramakesmusic/neuron-explorer",
        "title": "neuron-explorer: công cụ khám phá neuron",
        "author": "lyramakesmusic · GitHub", "group": "Bài viết gốc",
        "summary": "README của công cụ khám phá neuron MLP cho Qwen3.5-4B (tiếng Anh).",
    },
    {
        "id": "neeze-asr-neuron-128", "kind": "mdx",
        "url": f"{RAW}/Neeze/docs/main/src/content/docs/practical-ai/qwen3-asr-neuron-128.mdx",
        "page": "https://neeze.github.io/docs/practical-ai/qwen3-asr-neuron-128/",
        "title": "\"Mổ não\" model ASR và neuron 128 đáng ngờ",
        "author": "Neeze (Nam Nam)", "group": "Đọc thêm cùng tác giả",
        "summary": "Qwen3-ASR viết tiếng Việt thành chữ Thái: lần ra neuron 128 ở layer 22.",
    },
    {
        "id": "neeze-asr-lm-head", "kind": "mdx",
        "url": f"{RAW}/Neeze/docs/main/src/content/docs/practical-ai/qwen3-asr-lm-head-fix.mdx",
        "page": "https://neeze.github.io/docs/practical-ai/qwen3-asr-lm-head-fix/",
        "title": "Sửa đúng 1.024 con số, model ASR bớt viết tiếng Việt thành chữ Thái",
        "author": "Neeze (Nam Nam)", "group": "Đọc thêm cùng tác giả",
        "summary": "Phần tiếp: sửa một hàng của lm_head thay vì tắt neuron.",
    },
]
BY_ID = {d["id"]: d for d in CATALOG}


def _fetch(url: str, timeout=40) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _strip_front_matter(text: str):
    meta = {}
    m = re.match(r"^﻿?---\s*\n(.*?)\n---\s*\n", text, re.S)
    if m:
        for line in m.group(1).splitlines():
            kv = re.match(r"^([A-Za-z_]+):\s*(.*)$", line)
            if kv:
                meta[kv.group(1)] = kv.group(2).strip().strip("'\"")
        text = text[m.end():]
    return meta, text


class _HtmlToMarkdown(HTMLParser):
    """Chuyển trang blog HTML sang Markdown đơn giản (tiêu đề, đoạn, danh sách, bảng, hình, link)."""

    SKIP = {"script", "style", "svg", "head", "title", "noscript", "button", "template",
            "d-front-matter", "d-cite", "d-bibliography", "d-appendix", "canvas"}
    BLOCKS = {"p", "div", "section", "article", "figure", "details", "blockquote", "header",
              "footer", "main", "d-article", "d-title", "d-byline", "ul", "ol", "table", "aside"}

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.blocks = []  # (loại, nội dung)
        self.cur, self.prefix, self.kind = [], "", "p"
        self.skip = 0
        self.lists = []
        self.table = None
        self.cell = None
        self.links = []
        self.images = []  # (url tuyệt đối, tên file)
        self.pre = None

    def _emit(self, kind, text):
        self.blocks.append((kind, text))

    def _flush(self):
        text = re.sub(r"[ \t\r\n]+", " ", "".join(self.cur)).replace("\x00", "\n").strip()
        text = re.sub(r"\*\*\s*\*\*", "", text)
        self.cur = []
        if text:
            self._emit(self.kind, self.prefix + text)
        self.prefix, self.kind = "", "p"

    def _sink(self):
        return self.cell if self.cell is not None else self.cur

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag in self.SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if self.pre is not None:
            return
        if tag == "pre":
            self._flush()
            self.pre = []
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self.prefix = "#" * min(int(tag[1]) + 1, 6) + " "
        elif tag == "summary":
            self._flush()
            self.prefix = "#### "
        elif tag in ("ul", "ol"):
            self._flush()
            self.lists.append(tag)
        elif tag == "li":
            self._flush()
            depth = max(len(self.lists), 1)
            self.prefix = "  " * (depth - 1) + ("1. " if self.lists and self.lists[-1] == "ol" else "- ")
            self.kind = "li"
        elif tag == "table":
            self._flush()
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.table.append([])
        elif tag in ("td", "th") and self.table is not None:
            self.cell = []
        elif tag in self.BLOCKS:
            self._flush()
        elif tag == "figcaption":
            self._flush()
            self.kind = "caption"
        elif tag == "br":
            self._sink().append("\x00")
        elif tag in ("b", "strong"):
            self._sink().append(" **")
        elif tag in ("i", "em"):
            self._sink().append("*")
        elif tag == "code":
            self._sink().append("`")
        elif tag == "d-footnote":
            self._sink().append(" (Chú thích: ")
        elif tag == "a":
            href = a.get("href", "")
            if href and not href.startswith(("#", "javascript:")):
                self.links.append(urljoin(self.base, href))
                self._sink().append("[")
            else:
                self.links.append(None)
        elif tag == "img":
            src = a.get("src") or ""
            if src and not src.startswith("data:"):
                url = urljoin(self.base, src)
                name = re.sub(r"[^A-Za-z0-9._-]", "_", "_".join(urlsplit(url).path.split("/")[-2:]))[-100:]
                self.images.append((url, name))
                alt = (a.get("alt") or "").replace("]", "")
                self._flush()
                self._emit("img", f"![{alt}]({name})")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag == "pre" and self.pre is not None:
            code = "".join(self.pre).strip("\n")
            self.pre = None
            if code.strip():
                self._emit("pre", "```\n" + code + "\n```")
            return
        if self.pre is not None:
            return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6", "summary", "li", "figcaption"):
            if tag == "figcaption":
                text = re.sub(r"\s+", " ", "".join(self.cur)).strip()
                self.cur = [f"*{text}*"] if text else []
            self._flush()
        elif tag in ("ul", "ol"):
            self._flush()
            if self.lists:
                self.lists.pop()
        elif tag in ("td", "th") and self.cell is not None and self.table:
            text = re.sub(r"\s+", " ", "".join(self.cell)).replace("\x00", " ").strip().replace("|", "\\|")
            self.table[-1].append(text)
            self.cell = None
        elif tag == "table" and self.table is not None:
            rows = [r for r in self.table if any(c for c in r)]
            self.table = None
            if rows:
                n = max(len(r) for r in rows)
                rows = [r + [""] * (n - len(r)) for r in rows]
                lines = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * n]
                lines += ["| " + " | ".join(r) + " |" for r in rows[1:]]
                self._emit("table", "\n".join(lines))
        elif tag in self.BLOCKS:
            self._flush()
        elif tag in ("b", "strong"):
            self._sink().append("** ")
        elif tag in ("i", "em"):
            self._sink().append("*")
        elif tag == "code":
            self._sink().append("`")
        elif tag == "d-footnote":
            self._sink().append(")")
        elif tag == "a" and self.links:
            href = self.links.pop()
            if href:
                self._sink().append(f"]({href})")

    def handle_data(self, data):
        if self.skip:
            return
        if self.pre is not None:
            self.pre.append(data)
        else:
            self._sink().append(data)

    def markdown(self) -> str:
        self._flush()
        out, prev = [], None
        for kind, text in self.blocks:
            if out:
                out.append("\n" if kind == "li" and prev == "li" else "\n\n")
            out.append(text)
            prev = kind
        md = "".join(out)
        md = re.sub(r"\*\* +([^*]+?) +\*\*", r"**\1**", md)
        md = re.sub(r" +([,.;:!?)])", r"\1", md)
        return md.strip() + "\n"


class Docs:
    def __init__(self, data_dir: Path, bundled_dir: Path):
        self.dir = data_dir / "docs"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bundled = bundled_dir

    # ---------- Đọc ----------
    def _meta(self, doc_id):
        p = self.dir / doc_id / "meta.json"
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def catalog(self) -> list:
        out = []
        for d in CATALOG:
            item = {k: d.get(k) for k in ("id", "title", "author", "group", "summary", "page", "kind")}
            if d["kind"] == "bundled":
                item.update(downloaded=True, size=(self.bundled / d["file"]).stat().st_size, fetched=None)
            else:
                m = self._meta(d["id"])
                item.update(downloaded=bool(m), size=(m or {}).get("size", 0),
                            fetched=(m or {}).get("fetched"), images=(m or {}).get("images", 0))
            out.append(item)
        return out

    def read(self, doc_id: str):
        d = BY_ID.get(doc_id)
        if not d:
            return None
        if d["kind"] == "bundled":
            return {"id": doc_id, "markdown": (self.bundled / d["file"]).read_text(encoding="utf-8")}
        p = self.dir / doc_id / "doc.md"
        if not p.exists():
            return {"id": doc_id, "markdown": None}
        return {"id": doc_id, "markdown": p.read_text(encoding="utf-8"), "meta": self._meta(doc_id)}

    def asset_path(self, doc_id: str, name: str):
        if not ID_RE.match(doc_id or "") or not ASSET_RE.match(name or "") or name in ("doc.md", "meta.json"):
            return None
        p = (self.dir / doc_id / name).resolve()
        return p if p.is_file() and self.dir.resolve() in p.parents else None

    # ---------- Tải về ----------
    def download(self, doc_id: str) -> dict:
        d = BY_ID[doc_id]
        if d["kind"] == "bundled":
            return {"images": 0}
        tmp = self.dir / f".{doc_id}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir(parents=True)
        raw = _fetch(d["url"]).decode("utf-8", "replace")
        images = []
        if d["kind"] == "html":
            raw = re.sub(r"\{%.*?%\}", "", raw, flags=re.S)
            _, raw = _strip_front_matter(raw)
            conv = _HtmlToMarkdown(d["page"])
            conv.feed(raw)
            body = conv.markdown()
            images = [(u, n) for u, n in conv.images if n.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"))]
            md = body
        else:
            meta, body = _strip_front_matter(raw)
            base = d["url"].rsplit("/", 1)[0] + "/"
            page_base = d["page"] if d["page"].endswith("/") else d["page"] + "/"

            def img(m):
                alt, src = m.group(1), m.group(2).strip()
                if re.match(r"^https?://", src):
                    url = src
                else:
                    url = urljoin(base, src)
                name = re.sub(r"[^A-Za-z0-9._-]", "_", src.split("/")[-1].split("?")[0])[-100:] or "image"
                images.append((url, name))
                return f"![{alt}]({name})"

            body = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", img, body)
            body = re.sub(r"(?<!!)\[([^\]]+)\]\((?!https?://|#|mailto:)([^)\s]+)\)",
                          lambda m: f"[{m.group(1)}]({urljoin(page_base if d['kind'] == 'mdx' else d['page'] + '/blob/main/', m.group(2))})",
                          body)
            title = meta.get("title") or d["title"]
            head = f"# {title}\n\n"
            if meta.get("description"):
                head += f"> {meta['description']}\n\n"
            md = head + body.strip() + "\n"
            if d["kind"] == "hf" and d.get("code"):
                code = _fetch(d["code"]).decode("utf-8", "replace")
                md += f"\n## File `modeling_gemma3_vi.py`\n\n```python\n{code.rstrip()}\n```\n"

        saved = 0
        for url, name in dict((n, (u, n)) for u, n in images).values():
            try:
                (tmp / name).write_bytes(_fetch(url))
                saved += 1
            except Exception:
                pass
        (tmp / "doc.md").write_text(md, encoding="utf-8")
        meta = {"id": doc_id, "title": d["title"], "source": d["url"], "page": d["page"],
                "fetched": time.time(), "size": len(md.encode("utf-8")), "images": saved}
        (tmp / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
        final = self.dir / doc_id
        shutil.rmtree(final, ignore_errors=True)
        tmp.rename(final)
        return {"images": saved, "size": meta["size"]}

    def download_many(self, ids):
        for doc_id in ids:
            if doc_id not in BY_ID or BY_ID[doc_id]["kind"] == "bundled":
                continue
            yield {"id": doc_id, "status": "downloading"}
            try:
                r = self.download(doc_id)
                yield {"id": doc_id, "status": "ok", **r}
            except Exception as e:
                yield {"id": doc_id, "status": "error", "error": f"{type(e).__name__}: {e}"}

    def export_zip(self) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            index = ["# Bộ tài liệu AI Việt Studio\n"]
            for i, d in enumerate(CATALOG, 1):
                folder = f"{i:02d}-{d['id']}"
                if d["kind"] == "bundled":
                    z.writestr(f"Bo-tai-lieu/{folder}/{d['file']}", (self.bundled / d["file"]).read_bytes())
                    index.append(f"- {d['title']}: `{folder}/{d['file']}`")
                    continue
                src = self.dir / d["id"]
                if not (src / "doc.md").exists():
                    index.append(f"- {d['title']}: (chưa tải) {d['page']}")
                    continue
                for f in sorted(src.iterdir()):
                    if f.name == "meta.json":
                        continue
                    z.writestr(f"Bo-tai-lieu/{folder}/{f.name}", f.read_bytes())
                index.append(f"- {d['title']}: `{folder}/doc.md` (nguồn: {d['page']})")
            z.writestr("Bo-tai-lieu/MUC-LUC.md", "\n".join(index) + "\n")
        return buf.getvalue()
