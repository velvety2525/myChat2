"""규정 폴더의 파일을 읽어 텍스트로 변환한다."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_EXTS = {".pdf", ".docx", ".txt", ".md"}


@dataclass
class Document:
    source: str  # 폴더 기준 상대 경로
    text: str
    # (시작 오프셋, 페이지 번호) 목록. PDF만 채워진다.
    page_offsets: list[tuple[int, int]] = field(default_factory=list)

    def page_at(self, offset: int) -> int | None:
        page = None
        for start, num in self.page_offsets:
            if start > offset:
                break
            page = num
        return page


def _read_text_file(path: Path) -> str:
    for enc in ("utf-8-sig", "cp949", "euc-kr"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _read_pdf(path: Path) -> tuple[str, list[tuple[int, int]]]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    pos = 0
    for i, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        offsets.append((pos, i))
        parts.append(text)
        pos += len(text) + 2  # "\n\n" 구분자
    return "\n\n".join(parts), offsets


def _read_docx(path: Path) -> str:
    import docx

    d = docx.Document(str(path))
    lines = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text.strip() for cell in row.cells))
    return "\n".join(lines)


def load_document(path: Path, root: Path) -> Document | None:
    ext = path.suffix.lower()
    source = str(path.relative_to(root))
    if ext == ".pdf":
        text, offsets = _read_pdf(path)
        return Document(source, text, offsets)
    if ext == ".docx":
        return Document(source, _read_docx(path))
    if ext in (".txt", ".md"):
        return Document(source, _read_text_file(path))
    return None


def list_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted(
        p for p in root.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS and not p.name.startswith((".", "~$"))
    )
