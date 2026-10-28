"""규정 폴더를 읽어 .index_cache/chunks_*.json을 만든다 (웹 배포 전에 실행 후 커밋).

python scripts/build_index.py [규정 폴더]
"""
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rag.index import build_chunks  # noqa: E402

if __name__ == "__main__":
    docs = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "regulations"
    t = time.time()
    chunks, errors = build_chunks(docs, ROOT / ".index_cache")
    for e in errors:
        print("경고:", e)
    print(f"청크 {len(chunks)}개, 규정 {len({c.title or c.source for c in chunks})}개 ({time.time() - t:.1f}초)")
    print("이제 .index_cache/ 를 커밋하세요.")
