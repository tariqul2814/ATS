import io
import zipfile

import pytest
from docx import Document

from app.pipeline.errors import ExtractionEmptyError, ExtractionError
from app.pipeline.extract import FileType, detect_file_type, extract_text
from tests.conftest import ASSETS

PDF = (ASSETS / "sample_cv.pdf").read_bytes()
DOCX = (ASSETS / "sample_cv.docx").read_bytes()


def test_detects_types_from_content():
    assert detect_file_type(PDF) is FileType.PDF
    assert detect_file_type(DOCX) is FileType.DOCX


def test_rejects_unknown_content():
    with pytest.raises(ExtractionError):
        detect_file_type(b"just some text")


def test_rejects_zip_that_is_not_docx():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("readme.txt", "hello")
    with pytest.raises(ExtractionError):
        detect_file_type(buf.getvalue())


def test_pdf_text_extracted_in_order():
    text = extract_text(PDF, FileType.PDF)
    for expected in ("Alex Example", "Summary", "FastAPI", "2M requests/day", "Education"):
        assert expected in text
    assert text.index("Summary") < text.index("Experience") < text.index("Education")


def test_all_pdf_pages_read():
    text = extract_text((ASSETS / "sample_cv_3_pages.pdf").read_bytes(), FileType.PDF)
    for page in (1, 2, 3):
        assert f"Page {page} of 3" in text


def test_docx_keeps_headings_and_bullets():
    text = extract_text(DOCX, FileType.DOCX)
    lines = text.splitlines()
    assert "Experience" in lines
    assert "• Built payments API endpoints in FastAPI serving 2M requests/day." in lines
    assert text.index("Skills") < text.index("Experience")
    assert "\n\nEducation" in text  # blank line kept before a heading


def test_docx_tables_and_header_included():
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = "Sam Header · sam@example.com"
    doc.add_paragraph("Professional profile with plenty of words to pass the minimum length check here.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Skill", "Years"
    table.cell(1, 0).text, table.cell(1, 1).text = "Python", "5"
    buf = io.BytesIO()
    doc.save(buf)
    text = extract_text(buf.getvalue(), FileType.DOCX)
    assert text.splitlines()[0] == "Sam Header · sam@example.com"
    assert "Skill | Years" in text and "Python | 5" in text


def test_image_only_pdf_is_empty():
    with pytest.raises(ExtractionEmptyError) as err:
        extract_text((ASSETS / "blank.pdf").read_bytes(), FileType.PDF)
    assert err.value.reason == "extraction_empty"


@pytest.mark.parametrize(
    "data,file_type",
    [(b"%PDF-1.7 garbage that is not a pdf", FileType.PDF), (b"PK\x03\x04broken zip", FileType.DOCX)],
)
def test_corrupt_files_raise_extraction_error(data, file_type):
    with pytest.raises(ExtractionError) as err:
        extract_text(data, file_type)
    assert err.value.reason == "extraction_failed"


def test_truncated_pdf_raises_or_is_empty():
    with pytest.raises((ExtractionError, ExtractionEmptyError)):
        extract_text(PDF[: len(PDF) // 3], FileType.PDF)
