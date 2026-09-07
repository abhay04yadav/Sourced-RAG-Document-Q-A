"""PDF text extraction with PyMuPDF (page-aware)."""

from pathlib import Path

import fitz


def extract_pages(path: str | Path) -> list[tuple[int, str]]:
    """
    Extract text from each PDF page.

    Returns a list of (page_number, text) with 1-based page numbers.
    Page order matches the PDF; empty pages still appear with empty text.
    """
    pages: list[tuple[int, str]] = []
    with fitz.open(path) as doc:
        for index, page in enumerate(doc):
            text = page.get_text("text") or ""
            pages.append((index + 1, text))
    return pages
