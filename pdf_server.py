import json
import os
import tempfile
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from typing import Optional

from pdf_agent import extract_structured_info_from_pdf, ChatGLMClient, ExtractOptions


PORT = int(os.environ.get("PDF_AGENT_PORT", "8765"))


class Handler(BaseHTTPRequestHandler):
    def _set_headers(self, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ["/", "/extract"]:
            status = {
                "status": "ok",
                "endpoint": "/extract",
                "method": "POST",
                "content_type": "application/pdf",
                "query": {"max_pages": "int(optional)", "max_chars": "int(optional)"},
                "example": "curl -X POST -H \"Content-Type: application/pdf\" --data-binary @file.pdf http://127.0.0.1:8765/extract",
                "model": {"available": ChatGLMClient().available()},
            }
            self._set_headers(200)
            self.wfile.write(json.dumps(status, ensure_ascii=False).encode("utf-8"))
            return
        self._set_headers(404)
        self.wfile.write(json.dumps({"error": "not_found"}).encode("utf-8"))
        return

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/extract":
            self._set_headers(404)
            self.wfile.write(json.dumps({"error": "not_found"}).encode("utf-8"))
            return
        qs = parse_qs(parsed.query)
        max_pages = None
        try:
            if "max_pages" in qs:
                max_pages = int(qs["max_pages"][0])
        except Exception:
            max_pages = None
        max_chars = 80000
        try:
            if "max_chars" in qs:
                max_chars = int(qs["max_chars"][0])
        except Exception:
            max_chars = 80000

        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            self._set_headers(400)
            self.wfile.write(json.dumps({"error": "empty_body"}).encode("utf-8"))
            return
        body = self.rfile.read(length)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(body)
            tmp_path = Path(tmp.name)

        try:
            client = ChatGLMClient()
            if not client.available():
                raise RuntimeError("ChatGLM接口不可用")
            opt = ExtractOptions(max_pages=max_pages, max_chars=max_chars)
            result = extract_structured_info_from_pdf(tmp_path, client, opt)
            self._set_headers(200)
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
        except Exception as e:
            self._set_headers(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


def run():
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"PDF agent server listening on http://127.0.0.1:{PORT}/extract")
    server.serve_forever()


if __name__ == "__main__":
    run()

