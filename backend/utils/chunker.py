"""
Section-aware text chunking for large documents.

Unlike the original page-local windows, this builds a word stream that can
span page boundaries *within a section* (so a scene split across two pages is
not torn apart), but never merges across a detected chapter/heading break.

Each output chunk keeps:
- chunk_text: the window text
- page_number: the page the window *starts* on (used for citations)
- token_count: ~0.75 words-per-token estimate
- is_toc: True when the chunk comes from a table-of-contents-like page/section
"""

from __future__ import annotations

import re

# Lines that begin a new section. Kept conservative so we don't over-split.
_HEADING_RE = re.compile(r"^\s*(chapter|book|part)\b", re.IGNORECASE)


def estimate_token_count(text: str) -> int:
    """
    Approximate token count using ~0.75 words per token.

    Empty text -> 0; otherwise at least 1.
    """
    words = text.split()
    if not words:
        return 0
    return max(1, round(len(words) / 0.75))


def _is_heading_line(line: str) -> bool:
    """True for lines that look like a chapter/book/part heading."""
    return bool(_HEADING_RE.match(line.strip()))


def is_toc_page(text: str) -> bool:
    """
    Heuristic table-of-contents detector.

    A page is TOC-like when it mentions CONTENTS, or when it is mostly a list of
    short title-like lines (few words each). These pages pack many names/titles
    and otherwise dominate list/aggregate queries.
    """
    upper = text.upper()
    if "CONTENTS" in upper:
        return True

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) >= 8:
        short = sum(1 for ln in lines if len(ln.split()) <= 8)
        if short / len(lines) >= 0.85:
            return True
    return False


def chunk_pages(
    pages: list[tuple[int, str]],
    size: int = 800,
    overlap: int = 100,
) -> list[dict]:
    """
    Build section-aware sliding-window chunks from (page_number, text) pages.

    Windows slide across page boundaries but reset at detected headings. Each
    chunk records the page its first word came from. Empty pages contribute no
    text. Overlap applies within a section only.
    """
    if size <= 0:
        raise ValueError("size must be positive")
    if overlap < 0 or overlap >= size:
        raise ValueError("overlap must be >= 0 and < size")

    step = size - overlap

    # sections: list of (words_with_pages, is_toc)
    sections: list[tuple[list[tuple[int, str]], bool]] = []
    current: list[tuple[int, str]] = []
    current_is_toc = False

    def _flush() -> None:
        nonlocal current, current_is_toc
        if current:
            sections.append((current, current_is_toc))
        current = []
        current_is_toc = False

    for page_number, text in pages:
        if not text or not text.strip():
            continue

        page_is_toc = is_toc_page(text)

        for line in text.splitlines():
            if _is_heading_line(line):
                # Close the previous section and start a fresh one.
                _flush()
                current_is_toc = page_is_toc
            for word in line.split():
                current.append((page_number, word))

        # If any page in the running section is TOC-like, tag the section.
        if page_is_toc:
            current_is_toc = True

    _flush()

    results: list[dict] = []
    for words_with_pages, is_toc in sections:
        n = len(words_with_pages)
        if n == 0:
            continue

        start = 0
        while start < n:
            window = words_with_pages[start : start + size]
            chunk_text = " ".join(word for _, word in window)
            results.append(
                {
                    "chunk_text": chunk_text,
                    "page_number": window[0][0],
                    "token_count": estimate_token_count(chunk_text),
                    "is_toc": is_toc,
                }
            )
            if start + size >= n:
                break
            start += step

    return results
