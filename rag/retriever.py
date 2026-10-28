"""검색기: 한국어에 맞춘 BM25 키워드 검색 + (선택) Gemini 임베딩 의미 검색 하이브리드."""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path

from .chunker import Chunk

TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]+")
HANGUL_RE = re.compile(r"[가-힣]")


def tokenize(text: str) -> list[str]:
    """한국어는 조사·어미가 붙어 단어 일치가 잘 안 되므로 음절 bigram을 함께 쓴다."""
    tokens: list[str] = []
    for word in TOKEN_RE.findall(text.lower()):
        if HANGUL_RE.search(word):
            if len(word) == 1:
                tokens.append(word)
            else:
                tokens.extend(word[i : i + 2] for i in range(len(word) - 1))
        else:
            tokens.append(word)
    return tokens


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tfs = [Counter(d) for d in docs]
        self.lens = [len(d) for d in docs]
        self.avgdl = (sum(self.lens) / len(docs)) if docs else 0.0
        df: Counter[str] = Counter()
        for tf in self.tfs:
            df.update(tf.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        q = Counter(query)
        for tf, dl in zip(self.tfs, self.lens):
            s = 0.0
            norm = self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1))
            for t, qn in q.items():
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + norm) * qn
            out.append(s)
        return out


EMBED_MODEL = "gemini-embedding-001"


class GeminiEmbedder:
    """Gemini 임베딩. 결과는 디스크에 캐시해 같은 청크를 다시 임베딩하지 않는다."""

    def __init__(self, api_key: str, cache_dir: Path):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.cache_path = cache_dir / f"embeddings_{EMBED_MODEL}.json"
        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.cache: dict[str, list[float]] = json.loads(self.cache_path.read_text())
        except (OSError, ValueError):
            self.cache = {}

    def _embed(self, texts: list[str], task: str) -> list[list[float]]:
        from google.genai import types

        vecs: list[list[float]] = []
        for i in range(0, len(texts), 100):
            res = self.client.models.embed_content(
                model=EMBED_MODEL,
                contents=texts[i : i + 100],
                config=types.EmbedContentConfig(task_type=task, output_dimensionality=768),
            )
            vecs.extend(e.values for e in res.embeddings)
        return vecs

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        keys = [hashlib.sha1(t.encode()).hexdigest() for t in texts]
        missing = [(k, t) for k, t in zip(keys, texts) if k not in self.cache]
        if missing:
            new = self._embed([t for _, t in missing], "RETRIEVAL_DOCUMENT")
            for (k, _), v in zip(missing, new):
                self.cache[k] = v
            self.cache_path.write_text(json.dumps(self.cache))
        return [self.cache[k] for k in keys]

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY")[0]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class Retriever:
    def __init__(self, chunks: list[Chunk], embedder: GeminiEmbedder | None = None):
        self.chunks = chunks
        # 조문 제목과 파일명도 검색 대상에 포함
        self.bm25 = BM25([tokenize(f"{c.source} {c.article or ''} {c.text}") for c in chunks])
        self.embedder = embedder
        self.vectors = embedder.embed_documents([c.text for c in chunks]) if embedder and chunks else None

    def search(self, query: str, k: int = 6) -> list[tuple[Chunk, float]]:
        if not self.chunks:
            return []
        bm = self.bm25.scores(tokenize(query))
        if self.vectors is None:
            ranked = sorted(range(len(bm)), key=lambda i: bm[i], reverse=True)
            return [(self.chunks[i], bm[i]) for i in ranked[:k] if bm[i] > 0]

        # Reciprocal Rank Fusion으로 키워드/의미 검색 순위를 합친다
        qv = self.embedder.embed_query(query)
        sem = [_cosine(qv, v) for v in self.vectors]
        fused = [0.0] * len(self.chunks)
        for scores in (bm, sem):
            order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
            for rank, i in enumerate(order):
                fused[i] += 1.0 / (60 + rank)
        ranked = sorted(range(len(fused)), key=lambda i: fused[i], reverse=True)
        return [(self.chunks[i], fused[i]) for i in ranked[:k]]
