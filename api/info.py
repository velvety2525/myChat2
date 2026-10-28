"""GET /api/info — 색인된 규정 수와 사용 가능한 모델 정보."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.server import info  # noqa: E402


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        data = json.dumps(info(), ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
