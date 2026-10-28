"""규정 폴더 -> 청크 목록. 파일별 결과를 디스크에 캐시하고, 캐시만으로도 색인을 만들 수 있게 한다.

Vercel처럼 PDF를 다시 읽을 수 없는 환경에서는 저장소에 커밋된 캐시(.index_cache/chunks_*.json)만 읽는다.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path

from .chunker import Chunk, chunk_document
from .loader import list_files, load_document

CACHE_VERSION = "v1"


def _cache_file(path: Path, root: Path, cache_dir: Path) -> Path:
    # 키는 파일 내용 해시라서 git clone 후(수정 시각이 바뀌어도) 커밋된 캐시를 그대로 쓸 수 있다
    content_hash = hashlib.sha1(path.read_bytes()).hexdigest()
    key = hashlib.sha1(f"{CACHE_VERSION}|{path.relative_to(root)}|{content_hash}".encode()).hexdigest()
    return cache_dir / f"chunks_{key}.json"


def _read_cache(cache_file: Path) -> list[Chunk]:
    return [Chunk(**c) for c in json.loads(cache_file.read_text(encoding="utf-8"))]


def load_chunks_cached(path: Path, root: Path, cache_dir: Path) -> tuple[list[Chunk], Path]:
    """큰 PDF는 읽는 데 수 분이 걸리므로 파일별 청크 결과를 디스크에 캐시한다."""
    cache_file = _cache_file(path, root, cache_dir)
    try:
        return _read_cache(cache_file), cache_file
    except (OSError, ValueError, TypeError):
        pass
    doc = load_document(path, root)
    if not doc or not doc.text.strip():
        return [], cache_file
    chunks = chunk_document(doc, start_id=0)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(json.dumps([dataclasses.asdict(c) for c in chunks], ensure_ascii=False), encoding="utf-8")
    return chunks, cache_file


def build_chunks(docs_dir: Path, cache_dir: Path) -> tuple[list[Chunk], list[str]]:
    """규정 폴더의 모든 파일을 청크로 만든다. 지금 폴더에 없는 파일의 캐시는 지운다."""
    chunks: list[Chunk] = []
    errors: list[str] = []
    used: set[Path] = set()
    for path in list_files(docs_dir):
        try:
            file_chunks, cache_file = load_chunks_cached(path, docs_dir, cache_dir)
        except Exception as e:  # 손상된 파일 하나 때문에 전체가 멈추지 않도록
            errors.append(f"{path.name}: {e}")
            continue
        used.add(cache_file)
        if not file_chunks:
            errors.append(f"{path.name}: 텍스트를 추출하지 못했습니다 (스캔 이미지 PDF일 수 있음)")
        chunks.extend(file_chunks)
    for stale in cache_dir.glob("chunks_*.json"):
        if stale not in used:
            stale.unlink(missing_ok=True)
    for i, c in enumerate(chunks):
        c.id = i
    return chunks, errors


def load_prebuilt_chunks(cache_dir: Path) -> list[Chunk]:
    """원본 파일 없이 캐시 파일만으로 청크를 읽는다 (서버리스 배포용)."""
    chunks: list[Chunk] = []
    for f in sorted(cache_dir.glob("chunks_*.json")):
        chunks.extend(_read_cache(f))
    for i, c in enumerate(chunks):
        c.id = i
    return chunks
