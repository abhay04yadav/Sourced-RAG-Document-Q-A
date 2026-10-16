"""PDF text extraction with PyMuPDF (page-aware)."""

from pathlib import Path

import fitz


def extract_pages(source: str | Path | bytes) -> list[tuple[int, str]]:
    """
    Extract text from each PDF page. Accepts a file path or the raw PDF bytes.

    Returns a list of (page_number, text) with 1-based page numbers.
    Page order matches the PDF; empty pages still appear with empty text.
    """
    pages: list[tuple[int, str]] = []
    opened = fitz.open(stream=source, filetype="pdf") if isinstance(source, bytes) else fitz.open(source)
    with opened as doc:
        for index, page in enumerate(doc):
            text = page.get_text("text") or ""
            pages.append((index + 1, text))
    return pages
