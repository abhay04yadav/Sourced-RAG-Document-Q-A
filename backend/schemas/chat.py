"""Pydantic schemas for chat /ask and sessions."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AskRequest(BaseModel):
    """Body for POST /chat/ask."""

    document_id: uuid.UUID
    question: str = Field(min_length=1, max_length=4000)
    session_id: uuid.UUID | None = None


class SourceOut(BaseModel):
    """Citation payload returned with answers (Day 6 shape)."""

    chunk_index: int
    page_number: int
    chunk_text: str


class AskResponse(BaseModel):
    """Grounded answer plus retrieval sources."""

    session_id: uuid.UUID
    answer: str
    sources: list[SourceOut] = Field(default_factory=list)
    cached: bool = False


class MessageOut(BaseModel):
    """One persisted chat turn."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    role: str
    content: str
    source_chunks: list[dict[str, Any]] | None = None
    created_at: datetime


class SessionOut(BaseModel):
    """Session list item."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    created_at: datetime


class SessionDetail(SessionOut):
    """Session with ordered messages."""

    messages: list[MessageOut] = Field(default_factory=list)
