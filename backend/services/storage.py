"""
PDF storage: local disk (dev) or Supabase Storage (production, Day 8).

Hosts like Render wipe the local filesystem on every deploy/restart, so in
production the original PDFs live in a private Supabase Storage bucket.

documents.file_path records where each file lives:
- "supabase://<user_id>/<doc_id>.pdf"  -> object in SUPABASE_BUCKET
- anything else                        -> a local filesystem path

Both kinds can coexist in one database (local dev and production share it).
"""

from __future__ import annotations

import uuid
from pathlib import Path

import httpx

from core.config import settings

SUPABASE_PREFIX = "supabase://"


class StorageError(RuntimeError):
    """Raised when the storage backend cannot complete a request."""


def _object_key(user_id: uuid.UUID, doc_id: uuid.UUID) -> str:
    return f"{user_id}/{doc_id}.pdf"


# --- local -----------------------------------------------------------------


def local_path(doc) -> Path:
    """
    Locate a locally stored PDF.

    file_path is absolute and goes stale if the repo moves, so fall back to the
    canonical uploads/{user_id}/{doc_id}.pdf layout under the current UPLOAD_DIR.
    """
    path = Path(doc.file_path)
    if path.exists():
        return path
    return settings.upload_path / _object_key(doc.user_id, doc.id)


# --- supabase ----------------------------------------------------------------


def _supabase_url(key: str = "") -> str:
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_KEY:
        raise StorageError(
            "STORAGE_BACKEND=supabase needs SUPABASE_URL and SUPABASE_SERVICE_KEY."
        )
    base = settings.SUPABASE_URL.rstrip("/")
    url = f"{base}/storage/v1/object/{settings.SUPABASE_BUCKET}"
    return f"{url}/{key}" if key else url


def _headers(**extra: str) -> dict[str, str]:
    key = settings.SUPABASE_SERVICE_KEY
    return {"Authorization": f"Bearer {key}", "apikey": key, **extra}


def _check(response: httpx.Response, action: str) -> None:
    if response.status_code >= 400:
        raise StorageError(
            f"Supabase Storage {action} failed ({response.status_code}): {response.text[:300]}"
        )


# --- public API --------------------------------------------------------------


def save_pdf(user_id: uuid.UUID, doc_id: uuid.UUID, data: bytes) -> str:
    """Store the PDF and return the value to keep in documents.file_path."""
    key = _object_key(user_id, doc_id)
    if settings.STORAGE_BACKEND == "supabase":
        response = httpx.post(
            _supabase_url(key),
            content=data,
            headers=_headers(**{"Content-Type": "application/pdf", "x-upsert": "true"}),
            timeout=120,
        )
        _check(response, "upload")
        return SUPABASE_PREFIX + key

    dest = settings.upload_path / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return str(dest)


def read_pdf(doc) -> bytes:
    """Return the PDF bytes for a document, wherever it is stored."""
    if doc.file_path.startswith(SUPABASE_PREFIX):
        key = doc.file_path[len(SUPABASE_PREFIX):]
        response = httpx.get(_supabase_url(key), headers=_headers(), timeout=120)
        _check(response, "download")
        return response.content

    path = local_path(doc)
    if not path.exists():
        raise FileNotFoundError(f"Uploaded file missing: {path}")
    return path.read_bytes()


def pdf_exists(doc) -> bool:
    """True when the original PDF is still available (needed for reprocess)."""
    if doc.file_path.startswith(SUPABASE_PREFIX):
        key = doc.file_path[len(SUPABASE_PREFIX):]
        try:
            response = httpx.head(_supabase_url(key), headers=_headers(), timeout=30)
        except (httpx.HTTPError, StorageError):
            return False
        return response.status_code == 200
    return local_path(doc).exists()


def delete_pdf(doc) -> None:
    """Best-effort removal of the stored PDF (DB row deletion is the source of truth)."""
    if doc.file_path.startswith(SUPABASE_PREFIX):
        key = doc.file_path[len(SUPABASE_PREFIX):]
        try:
            httpx.request(
                "DELETE",
                _supabase_url(),
                headers=_headers(),
                json={"prefixes": [key]},
                timeout=30,
            )
        except (httpx.HTTPError, StorageError):
            pass
        return
    local_path(doc).unlink(missing_ok=True)
