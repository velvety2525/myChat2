"""Vercel 없이 웹 UI를 로컬에서 실행: python scripts/dev_server.py  ->  http://localhost:3000"""
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "api"))

import chat  # noqa: E402
import info  # noqa: E402


class DevHandler(chat.handler, info.handler, SimpleHTTPRequestHandler):
    """public/ 정적 파일 + Vercel 함수(api/*.py)를 한 서버에서 흉내 낸다."""

    def __init__(self, *args, **kwargs):
        SimpleHTTPRequestHandler.__init__(self, *args, directory=os.path.join(ROOT, "public"), **kwargs)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/info":
            return info.handler.do_GET(self)
        return SimpleHTTPRequestHandler.do_GET(self)

    def do_POST(self):
        if self.path.split("?")[0] == "/api/chat":
            return chat.handler.do_POST(self)
        self.send_error(404)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"http://localhost:{port}")
    ThreadingHTTPServer(("", port), DevHandler).serve_forever()
