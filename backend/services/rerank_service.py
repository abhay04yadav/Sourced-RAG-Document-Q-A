"""
Cross-encoder reranking + neighbor expansion.

Retrieve-then-rerank: hybrid search casts a cheap wide net; the cross-encoder
scores each (question, chunk) pair jointly (far more accurate than the
bi-encoder used for retrieval) but is too slow to run over the whole corpus.

The model is loaded once at import to avoid per-request load cost. With
RERANK_ENABLED=false (free-tier production) it is never loaded — torch is not
even imported — and rerank() keeps the hybrid RRF order instead.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings

# Load once per process — heavy init, do not move into rerank().
model = None
if settings.RERANK_ENABLED:
    from sentence_transformers import CrossEncoder  # local-only dependency (torch)

    model = CrossEncoder(settings.RERANKER_MODEL_NAME)

_SELECT_COLS = "id, chunk_text, chunk_index, page_number, page_end, token_count, is_toc"


def rerank(
    question: str,
    chunks: list[dict[str, Any]],
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """
    Score (question, chunk) pairs with the cross-encoder; return top_n by score.

    When reranking is disabled, returns the first top_n chunks in their incoming
    (RRF-fused) order.
    """
    if not chunks:
        return []
    top_n = top_n if top_n is not None else settings.RAG_CONTEXT_K
    if model is None:
        return chunks[:top_n]

    pairs = [(question, c["chunk_text"]) for c in chunks]
    scores = model.predict(pairs)

    scored = list(chunks)
    for chunk, score in zip(scored, scores, strict=True):
        chunk["rerank_score"] = float(score)

    scored.sort(key=lambda c: c["rerank_score"], reverse=True)
    return scored[:top_n]


def expand_neighbors(
    db: Session,
    doc_id: uuid.UUID,
    chunks: list[dict[str, Any]],
    window: int | None = None,
    cap: int | None = None,
) -> list[dict[str, Any]]:
    """
    Add adjacent chunk_index rows around each kept chunk.

    Keeps narrative/technical context that spans chunk boundaries (e.g. a scene
    split across pages). Result is deduped, capped, and sorted by chunk_index so
    the LLM reads it in document order.
    """
    window = window if window is not None else settings.RAG_NEIGHBOR_WINDOW
    cap = cap if cap is not None else settings.RAG_NEIGHBOR_CAP

    if not chunks:
        return chunks
    if window <= 0:
        return chunks[:cap]

    have = {c["chunk_index"] for c in chunks}
    wanted: set[int] = set()
    for c in chunks:
        for delta in range(-window, window + 1):
            if delta == 0:
                continue
            idx = c["chunk_index"] + delta
            if idx >= 0:
                wanted.add(idx)
    wanted -= have

    neighbors: list[dict[str, Any]] = []
    if wanted:
        sql = text(
            f"""
            SELECT {_SELECT_COLS}
            FROM document_chunks
            WHERE document_id = :doc_id
              AND chunk_index = ANY(:idxs)
            """
        )
        rows = db.execute(
            sql,
            {"doc_id": str(doc_id), "idxs": sorted(wanted)},
        ).mappings().all()
        neighbors = [dict(r) for r in rows]

    # Primary (reranked) chunks take priority for the cap; neighbors fill the rest.
    combined: list[dict[str, Any]] = list(chunks)
    seen = set(have)
    for n in neighbors:
        if n["chunk_index"] in seen:
            continue
        combined.append(n)
        seen.add(n["chunk_index"])

    combined = combined[:cap]
    combined.sort(key=lambda c: c["chunk_index"])
    return combined
