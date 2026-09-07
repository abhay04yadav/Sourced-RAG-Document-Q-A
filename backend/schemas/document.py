"""Pydantic schemas for documents and chunks."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ChunkOut(BaseModel):
    """Public chunk shape for detail responses."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    page_number: int
    token_count: int
    chunk_text: str


class DocumentOut(BaseModel):
    """List/upload response — no filesystem path exposed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: str
    page_count: int
    total_chunks: int
    error_message: str | None = None
    created_at: datetime


class DocumentDetail(DocumentOut):
    """GET /documents/{id} — includes ordered chunks for verify/citations preview."""

    chunks: list[ChunkOut] = Field(default_factory=list)
