"""Regenerate the sample CV files in this folder. Content is fictional.

    .venv\\Scripts\\python.exe tests\\assets\\make_assets.py
"""

from pathlib import Path

from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

HERE = Path(__file__).parent

CV = [
    ("h", "Alex Example"),
    ("p", "Backend Engineer · alex@example.com"),
    ("h", "Summary"),
    ("p", "Backend engineer with four years building Python REST APIs."),
    ("h", "Skills"),
    ("p", "Python, FastAPI, PostgreSQL, Docker, pytest"),
    ("h", "Experience"),
    ("p", "Acme Corp — Backend Engineer (2022–2026)"),
    ("b", "Built payments API endpoints in FastAPI serving 2M requests/day."),
    ("b", "Cut p95 latency by 40% by tuning PostgreSQL queries."),
    ("h", "Education"),
    ("p", "BSc Computer Science, Example University (2021)"),
]


def make_docx(path: Path) -> None:
    doc = Document()
    for kind, text in CV:
        if kind == "h":
            doc.add_heading(text, level=1)
        elif kind == "b":
            doc.add_paragraph(text, style="List Bullet")
        else:
            doc.add_paragraph(text)
    doc.save(path)


def make_pdf(path: Path, pages: int = 1) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    for page in range(pages):
        y = 800
        for kind, text in CV:
            c.setFont("Helvetica-Bold" if kind == "h" else "Helvetica", 12)
            c.drawString(50, y, ("• " if kind == "b" else "") + text.replace("·", "-").replace("—", "-").replace("–", "-"))
            y -= 22
        if pages > 1:
            c.drawString(50, y, f"Page {page + 1} of {pages}")
        c.showPage()
    c.save()


def make_blank_pdf(path: Path) -> None:
    """Image-only style PDF: a page with no text layer."""
    c = canvas.Canvas(str(path), pagesize=A4)
    c.rect(50, 500, 300, 200, fill=1)
    c.showPage()
    c.save()


if __name__ == "__main__":
    make_docx(HERE / "sample_cv.docx")
    make_pdf(HERE / "sample_cv.pdf")
    make_pdf(HERE / "sample_cv_3_pages.pdf", pages=3)
    make_blank_pdf(HERE / "blank.pdf")
    print("assets written to", HERE)
