"""Document upload, list, detail, and delete routes (Day 3–4)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from sqlalchemy import delete as sa_delete
from sqlalchemy import text
from sqlalchemy.orm import Session, joinedload

from api.deps import get_current_user
from core.config import _ENV_FILE, settings
from core.database import get_db
from models.document import Document
from models.user import User
from schemas.document import DocumentDetail, DocumentOut
from services.document_service import process_document

router = APIRouter()

_ALLOWED_MIME = {"application/pdf", "application/x-pdf"}
# Hard floor of 20 MB so a stale process / cached Settings cannot silently keep 10 MB.
_MIN_UPLOAD_BYTES = 20 * 1024 * 1024


def _max_upload_bytes() -> int:
    """Effective upload limit: max(20 MB, env/settings) so restarts cannot leave 10 MB active."""
    load_dotenv(_ENV_FILE, override=True, encoding="utf-8")
    raw = (os.getenv("MAX_UPLOAD_BYTES") or "").strip()
    configured = int(raw) if raw.isdigit() else int(settings.MAX_UPLOAD_BYTES)
    return max(configured, _MIN_UPLOAD_BYTES)


def _get_owned_document(db: Session, doc_id: uuid.UUID, user: User) -> Document:
    """Load a document owned by user, or raise 404 (IDOR-safe — no 403 leak)."""
    doc = db.get(Document, doc_id)
    if doc is None or doc.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return doc


def _validate_pdf_upload(file: UploadFile, data: bytes) -> None:
    """Require .pdf extension, PDF MIME type, size ≤ MAX_UPLOAD_BYTES, and %PDF magic."""
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .pdf files are allowed",
        )

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in _ALLOWED_MIME:
        # Some browsers send application/octet-stream; allow if magic bytes say PDF
        if content_type != "application/octet-stream":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid content type: {content_type}",
            )

    max_bytes = _max_upload_bytes()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File exceeds {max_bytes} bytes",
        )

    if not data.startswith(b"%PDF"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File content is not a valid PDF",
        )


@router.post(
    "/upload",
    response_model=DocumentOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    """
    Save a PDF and queue background extract → chunk → embed.

    Returns immediately with status='processing'. Day 4 background work sets
    status to 'ready' or 'failed'.
    """
    data = await file.read()
    _validate_pdf_upload(file, data)

    doc_id = uuid.uuid4()
    user_dir = settings.upload_path / str(current_user.id)
    user_dir.mkdir(parents=True, exist_ok=True)
    dest = user_dir / f"{doc_id}.pdf"
    dest.write_bytes(data)

    document = Document(
        id=doc_id,
        user_id=current_user.id,
        filename=file.filename or f"{doc_id}.pdf",
        file_path=str(dest),
        status="processing",
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    background_tasks.add_task(process_document, document.id)
    return document


@router.post("/{document_id}/reprocess", response_model=DocumentOut)
def reprocess_document(
    document_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    """
    Re-run extract -> chunk -> embed for an owned document.

    Needed after pipeline changes (new chunker / embedding model) so existing
    uploads are re-indexed without re-uploading the file. Sets status back to
    'processing'; background work overwrites chunks and sets ready/failed.
    """
    doc = _get_owned_document(db, document_id, current_user)

    if not Path(doc.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Original file is missing on disk; re-upload required",
        )

    doc.status = "processing"
    doc.error_message = None
    db.commit()
    db.refresh(doc)

    background_tasks.add_task(process_document, doc.id)
    return doc


@router.get("/", response_model=list[DocumentOut])
def list_documents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[Document]:
    """List documents owned by the current user (newest first)."""
    return (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )


@router.get("/{document_id}", response_model=DocumentDetail)
def get_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Document:
    """Return one owned document with its chunks ordered by chunk_index."""
    doc = (
        db.query(Document)
        .options(joinedload(Document.chunks))
        .filter(Document.id == document_id, Document.user_id == current_user.id)
        .first()
    )
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )
    return doc


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """
    Delete an owned document, cascade chunks/sessions, and remove the file.

    Uses a Core DELETE so Postgres ON DELETE CASCADE clears thousands of chunks
    in one statement. ORM session.delete() would emit per-row deletes and hit
    Supabase statement_timeout on large PDFs (e.g. Harry Potter omnibus).
    """
    doc = _get_owned_document(db, document_id, current_user)
    file_path = Path(doc.file_path)
    doc_id = doc.id

    # Detach so the ORM does not try to sync cascade deletes row-by-row.
    db.expunge(doc)

    try:
        # Large cascade deletes can exceed the default remote statement timeout.
        db.execute(text("SET LOCAL statement_timeout = '120s'"))
        result = db.execute(sa_delete(Document).where(Document.id == doc_id))
        if result.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete document: {exc}",
        ) from exc

    if file_path.exists():
        file_path.unlink(missing_ok=True)
