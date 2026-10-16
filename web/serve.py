#!/usr/bin/env python3
"""Static server with HTTP Range support + an API to fetch/align chapters.

Run under the alignment venv so the pipeline (torch, uroman) can be imported:
    align/.venv/bin/python web/serve.py

Endpoints:
    GET /api/catalog           -> {books:[{id,name,chapters,cached:[...]}]}
    GET /api/chapter?book=&ch= -> fetches+aligns if needed, returns {ok,slug}
Everything else is served statically (with Range support for audio seeking).
"""
import functools
import http.server
import json
import os
import re
import socketserver
import sys
import traceback
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "align"))
import pipeline  # noqa: E402

PORT = 8777


class RangeHandler(http.server.SimpleHTTPRequestHandler):
    def _json(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/catalog":
            books = []
            for b in pipeline.BOOKS:
                cached = [c for c in range(1, b[4] + 1)
                          if pipeline.is_cached(b[0], c)]
                books.append({"id": b[0], "name": b[1],
                              "chapters": b[4], "cached": cached})
            return self._json(200, {"books": books})
        if parsed.path == "/api/chapter":
            q = parse_qs(parsed.query)
            book = (q.get("book") or [""])[0]
            ch = (q.get("ch") or [""])[0]
            try:
                slug = pipeline.process_chapter(book, int(ch))
                return self._json(200, {"ok": True, "slug": slug})
            except Exception as e:
                traceback.print_exc()
                return self._json(400, {"ok": False, "error": str(e)})
        return super().do_GET()

    def send_head(self):
        rng = self.headers.get("Range")
        if not rng:
            return super().send_head()
        m = re.match(r"bytes=(\d+)-(\d*)", rng)
        if not m:
            return super().send_head()
        path = self.translate_path(self.path)
        if not os.path.isfile(path):
            return super().send_head()
        size = os.path.getsize(path)
        start = int(m.group(1))
        end = int(m.group(2)) if m.group(2) else size - 1
        end = min(end, size - 1)
        if start > end:
            self.send_error(416, "Requested Range Not Satisfiable")
            return None
        length = end - start + 1
        f = open(path, "rb")
        f.seek(start)
        self.send_response(206)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        self._range = (f, length)
        return f

    def copyfile(self, source, outputfile):
        rng = getattr(self, "_range", None)
        if not rng:
            return super().copyfile(source, outputfile)
        f, length = rng
        remaining = length
        try:
            while remaining > 0:
                chunk = f.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                outputfile.write(chunk)
                remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass  # client aborted the range request (e.g. audio seek) — harmless


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


if __name__ == "__main__":
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    handler = functools.partial(RangeHandler)
    with Server(("", PORT), handler) as httpd:
        print(f"Serving with Range support on http://localhost:{PORT}")
        httpd.serve_forever()
