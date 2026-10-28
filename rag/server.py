"""웹 API(Vercel 함수, 로컬 개발 서버)가 공유하는 요청 처리 로직."""
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

from .index import load_prebuilt_chunks
from .llm import CLAUDE_MODELS, GEMINI_MODELS, build_user_message, stream_claude, stream_gemini
from .retriever import Retriever

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".index_cache"
HISTORY_TURNS = 6
MAX_QUESTION_CHARS = 2000

PROVIDERS = {
    "claude": {"models": CLAUDE_MODELS, "env": "ANTHROPIC_API_KEY", "stream": stream_claude},
    "gemini": {"models": GEMINI_MODELS, "env": "GEMINI_API_KEY", "stream": stream_gemini},
}

_retriever: Retriever | None = None


def get_retriever() -> Retriever:
    # 함수 인스턴스가 살아 있는 동안 재사용 (콜드 스타트 때 한 번만 약 1초)
    global _retriever
    if _retriever is None:
        _retriever = Retriever(load_prebuilt_chunks(CACHE_DIR))
    return _retriever


def info() -> dict:
    r = get_retriever()
    titles = {c.title or c.source for c in r.chunks}
    return {
        "regulations": len(titles),
        "chunks": len(r.chunks),
        "providers": {
            name: {"models": p["models"], "serverKey": bool(os.environ.get(p["env"]))}
            for name, p in PROVIDERS.items()
        },
    }


class BadRequest(ValueError):
    pass


def chat_events(body: dict) -> Iterator[dict]:
    """질문 하나를 처리하며 {"type": "sources"|"delta"|"error"|"done", ...} 이벤트를 차례로 낸다."""
    provider = PROVIDERS.get(str(body.get("provider", "")).lower())
    if not provider:
        raise BadRequest("provider는 claude 또는 gemini 여야 합니다.")
    question = str(body.get("question", "")).strip()
    if not question:
        raise BadRequest("질문이 비어 있습니다.")
    if len(question) > MAX_QUESTION_CHARS:
        raise BadRequest(f"질문은 {MAX_QUESTION_CHARS}자 이하로 입력해 주세요.")
    api_key = str(body.get("apiKey") or "").strip() or os.environ.get(provider["env"], "")
    if not api_key:
        raise BadRequest("API 키가 없습니다. 설정에서 API 키를 입력해 주세요.")
    model = str(body.get("model") or provider["models"][0]).strip()[:100]
    try:
        top_k = max(3, min(15, int(body.get("topK", 6))))
    except (TypeError, ValueError):
        top_k = 6
    history = [
        {"role": m["role"], "content": str(m["content"])}
        for m in (body.get("history") or [])
        if isinstance(m, dict) and m.get("role") in ("user", "assistant") and m.get("content")
    ][-HISTORY_TURNS:]
    # Claude는 대화가 user로 시작해야 한다
    while history and history[0]["role"] != "user":
        history.pop(0)

    hits = get_retriever().search(question, k=top_k)
    yield {"type": "sources", "sources": [{"label": c.label, "text": c.text} for c, _ in hits]}
    try:
        for text in provider["stream"](api_key, model, history, build_user_message(question, hits)):
            yield {"type": "delta", "text": text}
    except Exception as e:
        yield {"type": "error", "message": _friendly_error(e)}
        return
    yield {"type": "done"}


def _friendly_error(e: Exception) -> str:
    msg = str(e)
    low = msg.lower()
    if "401" in msg or "authentication" in low or "api key not valid" in low or "api_key_invalid" in low:
        return "API 키가 올바르지 않습니다. 키를 다시 확인해 주세요."
    if "404" in msg or "not_found" in low or "not found" in low:
        return f"모델을 찾을 수 없습니다. 모델 이름을 확인해 주세요. ({msg[:200]})"
    if "429" in msg or "rate" in low or "quota" in low or "resource_exhausted" in low:
        return "요청 한도를 초과했습니다. 잠시 후 다시 시도하거나 요금제/크레딧을 확인해 주세요."
    if "credit" in low or "billing" in low:
        return "API 크레딧이 부족합니다. 결제 설정을 확인해 주세요."
    return f"모델 호출 중 오류가 발생했습니다: {msg[:300]}"
