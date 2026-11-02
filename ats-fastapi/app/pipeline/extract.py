"""Text extraction from PDF and DOCX (Req 4). Works on bytes; no web or LLM dependency.

Follows: file retrieval (file_store). Precedes: input preparation (prepare).
Every page/paragraph is read — there is no page cap; size is bounded later by prepare_input.
"""

import io
import zipfile
from enum import StrEnum

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from app.pipeline.errors import ExtractionEmptyError, ExtractionError

# Below this many non-whitespace characters the CV is treated as empty (e.g. a scanned, image-only
# PDF). OCR is out of scope (Q7).
MIN_TEXT_CHARS = 50


class FileType(StrEnum):
    """A supported CV file type, detected from the file's content signature."""

    PDF = "pdf"
    DOCX = "docx"


def detect_file_type(data: bytes) -> FileType:
    """Decide the type from the file's content signature, never from a caller-supplied type (Req 3.5)."""
    if data.startswith(b"%PDF-"):
        return FileType.PDF
    if data.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if "word/document.xml" in archive.namelist():
                    return FileType.DOCX
        except zipfile.BadZipFile:
            pass
    raise ExtractionError("unsupported or unrecognised file type")


def extract_text(data: bytes, file_type: FileType, min_chars: int = MIN_TEXT_CHARS) -> str:
    """Extract plain text from the CV bytes.

    Raises ExtractionError if the file cannot be parsed, ExtractionEmptyError if it yields fewer
    than `min_chars` non-whitespace characters (e.g. an image-only PDF).
    """
    try:
        text = _extract_pdf(data) if file_type is FileType.PDF else _extract_docx(data)
    except (ExtractionError, ExtractionEmptyError):
        raise
    except Exception as exc:  # noqa: BLE001 — parser libraries raise many types on corrupt input
        raise ExtractionError(f"could not read {file_type.value}: {type(exc).__name__}") from None
    if len("".join(text.split())) < min_chars:
        raise ExtractionEmptyError("no extractable text (image-only or empty document)")
    return text


def _extract_pdf(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    if reader.is_encrypted and not reader.decrypt(""):
        raise ExtractionError("PDF is password protected")
    pages = [(page.extract_text() or "").strip() for page in reader.pages]
    return "\n\n".join(p for p in pages if p)


def _extract_docx(data: bytes) -> str:
    doc = Document(io.BytesIO(data))
    lines: list[str] = []
    for section in doc.sections:  # contact details often live in the page header
        lines += [p.text.strip() for p in section.header.paragraphs if p.text.strip()]
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            line = _paragraph_line(block)
            if line:
                lines.append(line)
        elif isinstance(block, Table):
            lines += _table_lines(block)
    return "\n".join(_dedupe_adjacent(lines))


def _paragraph_line(paragraph: Paragraph) -> str:
    text = paragraph.text.strip()
    if not text:
        return ""
    style = (paragraph.style.name if paragraph.style is not None else "") or ""
    if style.startswith(("Heading", "Title")):
        return f"\n{text}"  # blank line before a heading keeps sections visible
    numbered = paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None
    if style.startswith("List") or numbered:
        return f"• {text}"
    return text


def _table_lines(table: Table) -> list[str]:
    lines = []
    for row in table.rows:
        cells: list[str] = []
        for cell in row.cells:
            value = " ".join(cell.text.split())
            if value and (not cells or cells[-1] != value):  # merged cells repeat their text
                cells.append(value)
        if cells:
            lines.append(" | ".join(cells))
    return lines


def _dedupe_adjacent(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if not out or out[-1] != line:
            out.append(line)
    return out
