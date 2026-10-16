"""Background document processing: extract → chunk → embed → store."""

from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import delete

from core.config import settings
from core.database import SessionLocal
from models.chunk import Chunk
from models.document import Document
from services.embedding_service import embed_many
from utils.chunker import chunk_pages
from utils.pdf_parser import extract_pages


def process_document(document_id: uuid.UUID) -> None:
    """
    Process one uploaded PDF in a fresh DB session.

    On success: inserts chunks with embeddings and sets status='ready'.
    On any failure: sets status='failed' and stores error_message.
    """
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return

        path = Path(doc.file_path)
        if not path.exists():
            raise FileNotFoundError(f"Uploaded file missing: {path}")

        # Idempotent: clear any prior chunks before re-insert
        db.execute(delete(Chunk).where(Chunk.document_id == document_id))
        db.flush()

        pages = extract_pages(path)
        chunk_dicts = chunk_pages(
            pages,
            size=settings.CHUNK_SIZE,
            overlap=settings.CHUNK_OVERLAP,
        )

        # A 'ready' doc with zero chunks can only ever refuse — fail loudly instead.
        if not chunk_dicts:
            raise ValueError(
                "No extractable text found in this PDF "
                "(scanned/image-only PDFs need OCR, which is not supported)."
            )

        # Passages are embedded without the query instruction prefix.
        embeddings = embed_many([c["chunk_text"] for c in chunk_dicts])
        for index, (item, embedding) in enumerate(zip(chunk_dicts, embeddings, strict=True)):
            db.add(
                Chunk(
                    document_id=document_id,
                    chunk_text=item["chunk_text"],
                    chunk_index=index,
                    page_number=item["page_number"],
                    token_count=item["token_count"],
                    is_toc=bool(item.get("is_toc", False)),
                    embedding=embedding,
                )
            )

        doc.page_count = len(pages)
        doc.total_chunks = len(chunk_dicts)
        doc.status = "ready"
        doc.error_message = None
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            doc = db.get(Document, document_id)
            if doc is not None:
                doc.status = "failed"
                doc.error_message = str(exc)[:2000]
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
