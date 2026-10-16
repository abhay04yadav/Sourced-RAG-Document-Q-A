"""
Add document_chunks.page_end and backfill exact values for existing documents.

The backfill re-runs extraction + chunking (cheap) on each stored PDF and copies
page_end onto the matching chunk_index, verifying the chunk text matches. No
re-embedding. Documents whose stored chunks don't match the current chunker keep
page_end = page_number; reprocess those (POST /documents/{id}/reprocess).

Usage (from repo root or backend/):

    backend\\venv\\Scripts\\python.exe backend\\scripts\\run_migrate_page_end.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import text

from core.config import settings
from core.database import engine
from scripts.run_migrate_hybrid import _statements
from services.storage import local_path
from utils.chunker import chunk_pages
from utils.pdf_parser import extract_pages

SQL_PATH = Path(__file__).with_name("migrate_page_end.sql")


def _backfill(conn) -> None:
    docs = conn.execute(
        text("SELECT id, user_id, filename, file_path FROM documents WHERE status = 'ready'")
    ).all()
    for doc_id, user_id, filename, file_path in docs:
        file_path = local_path(SimpleNamespace(id=doc_id, user_id=user_id, file_path=file_path))
        if not file_path.exists():
            print(f"  skip {filename}: file missing")
            continue

        stored = conn.execute(
            text(
                "SELECT chunk_index, chunk_text FROM document_chunks "
                "WHERE document_id = :d ORDER BY chunk_index"
            ),
            {"d": doc_id},
        ).all()
        fresh = chunk_pages(
            extract_pages(file_path),
            size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
        )
        same = len(stored) == len(fresh) and all(
            row.chunk_text == item["chunk_text"] for row, item in zip(stored, fresh)
        )
        if not same:
            print(f"  skip {filename}: chunks differ from current chunker -> reprocess")
            continue

        conn.execute(
            text(
                "UPDATE document_chunks SET page_end = :e "
                "WHERE document_id = :d AND chunk_index = :i"
            ),
            [
                {"e": item["page_end"], "d": doc_id, "i": i}
                for i, item in enumerate(fresh)
            ],
        )
        spans = sum(1 for item in fresh if item["page_end"] != item["page_number"])
        print(f"  {filename}: {len(fresh)} chunks, {spans} span a page break")


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for stmt in _statements(sql):
            conn.execute(text(stmt))
        print("page_end column ready; backfilling...")
        conn.execute(text("SET LOCAL statement_timeout = '300s'"))
        _backfill(conn)
    print("Done:", SQL_PATH.name)


if __name__ == "__main__":
    main()
