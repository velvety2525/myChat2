"""POST /api/chat — 규정 검색 후 LLM 답변을 NDJSON 스트림으로 보낸다."""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag.server import BadRequest, chat_events  # noqa: E402

MAX_BODY_BYTES = 200_000


class handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY_BYTES:
            return self._json(400, {"error": "요청 본문이 비었거나 너무 큽니다."})
        try:
            body = json.loads(self.rfile.read(length))
            events = chat_events(body if isinstance(body, dict) else {})
            first = next(events)  # 입력 검증 오류는 스트림 시작 전에 400으로 돌려준다
        except (ValueError, BadRequest) as e:
            return self._json(400, {"error": str(e) if isinstance(e, BadRequest) else "JSON 형식이 올바르지 않습니다."})

        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        for event in _chain(first, events):
            self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode())
            self.wfile.flush()


def _chain(first, rest):
    yield first
    yield from rest
