"""문서를 검색 단위(청크)로 나눈다.

규정 문서는 '제N조' 단위로 나누는 것이 가장 자연스러우므로 조문 단위 분할을 우선하고,
조문 구조가 없거나 조문이 너무 길면 글자 수 기준으로 겹치게 자른다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from .loader import Document

ARTICLE_RE = re.compile(r"^[ \t]*(제\s*\d+\s*조(?:\s*의\s*\d+)?)\s*(?:\(([^)\n]*)\))?", re.MULTILINE)
CHAPTER_RE = re.compile(r"^[ \t]*(제\s*\d+\s*[장절편])[^\n]*", re.MULTILINE)


@dataclass
class Chunk:
    id: int
    source: str
    text: str
    article: str | None = None  # 예: "제5조(연차휴가)"
    page: int | None = None

    @property
    def label(self) -> str:
        parts = [self.source]
        if self.article:
            parts.append(self.article)
        if self.page:
            parts.append(f"p.{self.page}")
        return " · ".join(parts)


def _split_by_size(text: str, size: int, overlap: int) -> list[tuple[int, str]]:
    """(시작 오프셋, 텍스트) 목록. 가능하면 줄바꿈/문장 경계에서 자른다."""
    out: list[tuple[int, str]] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + size, n)
        if end < n:
            window = text[start:end]
            cut = max(window.rfind("\n"), window.rfind(". "), window.rfind("다. "))
            if cut > size // 2:
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            out.append((start, piece))
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return out


def chunk_document(doc: Document, start_id: int, size: int = 900, overlap: int = 150) -> list[Chunk]:
    text = doc.text
    chunks: list[Chunk] = []
    matches = list(ARTICLE_RE.finditer(text))

    def add(offset: int, piece: str, article: str | None, chapter: str | None):
        body = piece if not chapter else f"[{chapter}]\n{piece}"
        chunks.append(Chunk(start_id + len(chunks), doc.source, body, article, doc.page_at(offset)))

    if len(matches) < 2:
        for off, piece in _split_by_size(text, size, overlap):
            add(off, piece, None, None)
        return chunks

    # 첫 조문 이전 부분(제목, 목적 등)
    preamble = text[: matches[0].start()].strip()
    if preamble:
        for off, piece in _split_by_size(preamble, size, overlap):
            add(off, piece, None, None)

    chapters = [(m.start(), m.group(0).strip()) for m in CHAPTER_RE.finditer(text)]
    for i, m in enumerate(matches):
        a_start = m.start()
        a_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        # 다음 조문 앞에 붙은 '제N장' 제목은 이 조문 본문에서 제외
        article_text = CHAPTER_RE.sub("", text[a_start:a_end]).strip()
        num = re.sub(r"\s+", "", m.group(1))
        article = f"{num}({m.group(2).strip()})" if m.group(2) else num
        chapter = None
        for c_off, c_title in chapters:
            if c_off <= a_start:
                chapter = c_title
        if len(article_text) <= size * 1.5:
            add(a_start, article_text, article, chapter)
        else:
            for off, piece in _split_by_size(article_text, size, overlap):
                if not piece.startswith(m.group(1)):
                    piece = f"({article} 계속)\n{piece}"
                add(a_start + off, piece, article, chapter)
    return chunks
