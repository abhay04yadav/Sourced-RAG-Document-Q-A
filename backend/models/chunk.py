"""Chunk ORM model — page-aware text segments with embeddings (Day 3–4)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import Base

if TYPE_CHECKING:
    from models.document import Document


class Chunk(Base):
    """
    One text chunk; may span pages within a section.

    page_number..page_end is the page range the chunk covers (used for citations).
    embedding is a 384-dim vector (BGE-small).
    """

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    page_end: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # True when the chunk comes from a table-of-contents page; down-weighted at retrieval.
    is_toc: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(384), nullable=False)

    document: Mapped[Document] = relationship("Document", back_populates="chunks")
