"""규정 기반 RAG 챗봇 (Streamlit)."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
from pathlib import Path

import streamlit as st

from rag.chunker import Chunk, chunk_document
from rag.llm import CLAUDE_MODELS, GEMINI_MODELS, build_user_message, stream_claude, stream_gemini
from rag.loader import SUPPORTED_EXTS, list_files, load_document
from rag.retriever import GeminiEmbedder, Retriever

APP_DIR = Path(__file__).parent
DEFAULT_DOCS_DIR = os.environ.get("REGULATIONS_DIR", str(APP_DIR / "regulations"))
CACHE_DIR = APP_DIR / ".index_cache"
HISTORY_TURNS = 6  # LLM에 넘길 이전 대화 메시지 수

st.set_page_config(page_title="규정 챗봇", page_icon="📘", layout="wide")


def _secret(name: str) -> str:
    try:
        return st.secrets.get(name, "") or os.environ.get(name, "")
    except Exception:
        return os.environ.get(name, "")


def load_chunks_cached(path: Path, root: Path) -> list[Chunk]:
    """큰 PDF는 읽는 데 수 분이 걸리므로 파일별 청크 결과를 디스크에 캐시한다."""
    stat = path.stat()
    key = hashlib.sha1(f"v1|{path.relative_to(root)}|{stat.st_mtime}|{stat.st_size}".encode()).hexdigest()
    cache_file = CACHE_DIR / f"chunks_{key}.json"
    try:
        return [Chunk(**c) for c in json.loads(cache_file.read_text(encoding="utf-8"))]
    except (OSError, ValueError, TypeError):
        pass
    doc = load_document(path, root)
    if not doc or not doc.text.strip():
        return []
    chunks = chunk_document(doc, start_id=0)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps([dataclasses.asdict(c) for c in chunks], ensure_ascii=False), encoding="utf-8")
    return chunks


@st.cache_resource(show_spinner="규정 문서를 읽고 색인하는 중... (큰 PDF는 처음 한 번만 수 분 걸립니다)")
def build_index(docs_dir: str, fingerprint: tuple, gemini_key: str | None):
    root = Path(docs_dir)
    chunks, errors = [], []
    for path in list_files(root):
        try:
            file_chunks = load_chunks_cached(path, root)
        except Exception as e:  # 손상된 파일 하나 때문에 전체가 멈추지 않도록
            errors.append(f"{path.name}: {e}")
            continue
        if not file_chunks:
            errors.append(f"{path.name}: 텍스트를 추출하지 못했습니다 (스캔 이미지 PDF일 수 있음)")
        for c in file_chunks:
            c.id = len(chunks)
            chunks.append(c)
    embedder = GeminiEmbedder(gemini_key, CACHE_DIR) if gemini_key else None
    return Retriever(chunks, embedder), errors


def folder_fingerprint(docs_dir: str) -> tuple:
    root = Path(docs_dir)
    return tuple((str(p.relative_to(root)), p.stat().st_mtime, p.stat().st_size) for p in list_files(root))


# ---------------- 사이드바 ----------------
with st.sidebar:
    st.header("⚙️ 설정")
    provider = st.radio("모델 제공사", ["Claude", "Gemini"], horizontal=True)
    if provider == "Claude":
        api_key = st.text_input("Claude API Key", value=_secret("ANTHROPIC_API_KEY"), type="password",
                                help="console.anthropic.com 에서 발급. 입력값은 이 세션에서만 사용됩니다.")
        models = CLAUDE_MODELS
    else:
        api_key = st.text_input("Gemini API Key", value=_secret("GEMINI_API_KEY"), type="password",
                                help="aistudio.google.com 에서 발급")
        models = GEMINI_MODELS
    model = st.selectbox("모델", models + ["직접 입력"])
    if model == "직접 입력":
        model = st.text_input("모델 ID", placeholder=models[0])

    st.divider()
    st.subheader("📂 규정 폴더")
    docs_dir = st.text_input("폴더 경로", value=DEFAULT_DOCS_DIR)
    top_k = st.slider("검색할 조항 수", 3, 15, 6)

    gemini_key_for_embed = None
    if provider == "Gemini" and api_key:
        if st.toggle("의미 검색 함께 사용 (Gemini 임베딩)", value=False,
                     help="키워드 검색에 Gemini 임베딩 기반 의미 검색을 결합합니다. 문서가 많으면 처음 임베딩에 시간이 걸리고 무료 등급 한도에 걸릴 수 있습니다."):
            gemini_key_for_embed = api_key

    if st.button("🔄 다시 색인", use_container_width=True):
        build_index.clear()

    files = list_files(Path(docs_dir))
    try:
        retriever, load_errors = build_index(docs_dir, folder_fingerprint(docs_dir), gemini_key_for_embed)
    except Exception as e:
        st.error(f"색인 실패: {e}")
        retriever, load_errors = Retriever([]), []

    st.caption(f"문서 {len(files)}개 · 청크 {len(retriever.chunks)}개")
    with st.expander("문서 목록"):
        for p in files:
            st.write("•", p.relative_to(docs_dir))
        if not files:
            st.write(f"지원 형식({', '.join(sorted(SUPPORTED_EXTS))})의 파일이 없습니다.")
    for err in load_errors:
        st.warning(err)

    if st.button("🗑️ 대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

# ---------------- 본문 ----------------
st.title("📘 규정 챗봇")
st.caption("규정 폴더의 문서를 근거로 답변합니다. 답변의 [출처]를 꼭 확인하세요.")

if "messages" not in st.session_state:
    st.session_state.messages = []


def render_sources(hits):
    with st.expander(f"📎 참고한 규정 {len(hits)}건"):
        for n, h in enumerate(hits, 1):
            st.markdown(f"**{n}. {h['label']}**")
            st.text(h["text"])


for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m.get("sources"):
            render_sources(m["sources"])

question = st.chat_input("규정에 대해 질문하세요 (예: 연차휴가는 며칠인가요?)")
if question:
    with st.chat_message("user"):
        st.markdown(question)

    with st.chat_message("assistant"):
        if not api_key:
            st.error(f"사이드바에 {provider} API Key를 입력해 주세요.")
            st.stop()
        if not retriever.chunks:
            st.error("색인된 규정 문서가 없습니다. 규정 폴더에 파일을 넣고 '다시 색인'을 눌러 주세요.")
            st.stop()

        try:
            hits = retriever.search(question, k=top_k)
        except Exception as e:
            st.error(f"검색 중 오류: {e}")
            st.stop()

        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages][-HISTORY_TURNS:]
        user_msg = build_user_message(question, hits)
        stream = stream_claude if provider == "Claude" else stream_gemini
        try:
            answer = st.write_stream(stream(api_key, model, history, user_msg))
        except Exception as e:
            st.error(f"모델 호출 오류: {e}")
            st.stop()

        sources = [{"label": c.label, "text": c.text} for c, _ in hits]
        if sources:
            render_sources(sources)

    st.session_state.messages.append({"role": "user", "content": question})
    st.session_state.messages.append({"role": "assistant", "content": answer, "sources": sources})
