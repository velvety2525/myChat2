"""Claude / Gemini 호출 (스트리밍)."""
from __future__ import annotations

from collections.abc import Iterator

from .chunker import Chunk

CLAUDE_MODELS = ["claude-sonnet-5-5", "claude-opus-5-5", "claude-haiku-5-5"]
GEMINI_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.5-flash-lite"]

SYSTEM_PROMPT = """당신은 회사 규정 안내 챗봇입니다. 아래 <규정> 태그 안에 검색된 규정 원문 발췌만을 근거로 사용자 질문에 답하세요.

규칙:
1. 반드시 제공된 규정 발췌에 있는 내용으로만 답하고, 추측하거나 일반 상식으로 채우지 마세요.
2. 답변의 각 핵심 내용 뒤에 근거를 [문서명 제N조] 형식으로 표시하세요. (조문 정보가 없으면 [문서명 p.N] 또는 [문서명])
3. 발췌에서 답을 찾을 수 없으면 "제공된 규정에서 해당 내용을 찾을 수 없습니다."라고 말하고, 관련 있어 보이는 조항이 있으면 함께 안내하세요.
4. 규정 간 내용이 충돌하거나 해석이 필요한 경우 그 점을 명확히 밝히세요.
5. 한국어로 간결하고 정확하게 답하세요. 수치·기간·요건은 원문 그대로 인용하세요."""


def build_context(hits: list[tuple[Chunk, float]]) -> str:
    blocks = [f'<발췌 번호="{n}" 출처="{c.label}">\n{c.text}\n</발췌>' for n, (c, _) in enumerate(hits, 1)]
    return "<규정>\n" + "\n\n".join(blocks) + "\n</규정>"


def build_user_message(question: str, hits: list[tuple[Chunk, float]]) -> str:
    if not hits:
        return f"<규정>\n(검색된 규정 발췌 없음)\n</규정>\n\n질문: {question}"
    return f"{build_context(hits)}\n\n질문: {question}"


def stream_claude(api_key: str, model: str, history: list[dict], user_msg: str, max_tokens: int = 2048) -> Iterator[str]:
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    messages = [{"role": m["role"], "content": m["content"]} for m in history]
    messages.append({"role": "user", "content": user_msg})
    with client.messages.stream(model=model, max_tokens=max_tokens, system=SYSTEM_PROMPT, messages=messages) as stream:
        yield from stream.text_stream


def stream_gemini(api_key: str, model: str, history: list[dict], user_msg: str, max_tokens: int = 8192) -> Iterator[str]:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    contents = [
        types.Content(role="model" if m["role"] == "assistant" else "user", parts=[types.Part(text=m["content"])])
        for m in history
    ]
    contents.append(types.Content(role="user", parts=[types.Part(text=user_msg)]))
    # 2.5 계열은 사고(thinking) 토큰도 출력 한도에 포함되므로 여유 있게 잡는다
    config = types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT, temperature=0.2, max_output_tokens=max_tokens)
    for chunk in client.models.generate_content_stream(model=model, contents=contents, config=config):
        if chunk.text:
            yield chunk.text
