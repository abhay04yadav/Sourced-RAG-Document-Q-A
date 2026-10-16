"""
RAG retrieval helpers.

Standard pipeline pieces:
- dense_search      : pgvector cosine nearest-neighbours for one query vector
- keyword_search    : Postgres full-text (BM25-ish) ranking
- reciprocal_rank_fusion : merge many ranked lists by rank, not raw score
- hybrid_search     : dense (multi-query) + sparse -> RRF -> candidates
- build_prompt      : strict grounded prompt with [Chunk N] citation markers

Rows are keyed by chunk id so the same chunk retrieved by multiple lists fuses
into a single candidate.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings

REFUSAL_MESSAGE = "I don't have that information in the uploaded document."

# Columns selected for every retrieval path so downstream stages share a shape.
_SELECT_COLS = "id, chunk_text, chunk_index, page_number, page_end, token_count, is_toc"


def _vector_literal(qvec: list[float]) -> str:
    """Format a Python float list as a pgvector literal string."""
    return "[" + ",".join(str(float(x)) for x in qvec) + "]"


def dense_search(
    db: Session,
    doc_id: uuid.UUID,
    qvec: list[float],
    k: int,
) -> list[dict[str, Any]]:
    """Top-k chunks for one query vector by cosine distance (<=>)."""
    sql = text(
        f"""
        SELECT {_SELECT_COLS}
        FROM document_chunks
        WHERE document_id = :doc_id
        ORDER BY embedding <=> CAST(:qvec AS vector)
        LIMIT :k
        """
    )
    rows = db.execute(
        sql,
        {"doc_id": str(doc_id), "qvec": _vector_literal(qvec), "k": k},
    ).mappings().all()
    return [dict(row) for row in rows]


def keyword_search(
    db: Session,
    doc_id: uuid.UUID,
    query: str,
    k: int,
) -> list[dict[str, Any]]:
    """Top-k chunks by Postgres full-text rank (handles exact terms/names/numbers)."""
    if not query.strip():
        return []
    sql = text(
        f"""
        SELECT {_SELECT_COLS},
               ts_rank(tsv, plainto_tsquery('english', :q)) AS rank
        FROM document_chunks
        WHERE document_id = :doc_id
          AND tsv @@ plainto_tsquery('english', :q)
        ORDER BY rank DESC
        LIMIT :k
        """
    )
    rows = db.execute(
        sql,
        {"doc_id": str(doc_id), "q": query, "k": k},
    ).mappings().all()
    return [dict(row) for row in rows]


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]],
    k: int = 60,
    toc_penalty: float = 1.0,
) -> list[dict[str, Any]]:
    """
    Fuse ranked lists with RRF: score = sum 1 / (k + rank), rank starting at 1.

    Chunks are identified by id. TOC chunks get their fused score multiplied by
    toc_penalty (< 1 to down-rank contents pages).
    """
    scores: dict[Any, float] = {}
    rep: dict[Any, dict[str, Any]] = {}

    for ranked in ranked_lists:
        for rank, row in enumerate(ranked, start=1):
            cid = row["id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in rep:
                rep[cid] = row

    for cid, row in rep.items():
        if row.get("is_toc"):
            scores[cid] *= toc_penalty

    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    fused: list[dict[str, Any]] = []
    for cid, score in ordered:
        item = dict(rep[cid])
        item["rrf_score"] = score
        fused.append(item)
    return fused


def hybrid_search(
    db: Session,
    doc_id: uuid.UUID,
    query_vectors: list[list[float]],
    query_text: str,
    dense_k: int | None = None,
    sparse_k: int | None = None,
    rrf_k: int | None = None,
    candidate_k: int | None = None,
) -> list[dict[str, Any]]:
    """
    Multi-query dense + single sparse retrieval fused with RRF.

    Each query vector contributes its own ranked dense list; the raw question
    drives one sparse list. Returns up to candidate_k fused candidates.
    """
    dense_k = dense_k if dense_k is not None else settings.RAG_DENSE_K
    sparse_k = sparse_k if sparse_k is not None else settings.RAG_SPARSE_K
    rrf_k = rrf_k if rrf_k is not None else settings.RAG_RRF_K
    candidate_k = candidate_k if candidate_k is not None else settings.RAG_CANDIDATE_K

    ranked_lists: list[list[dict[str, Any]]] = []
    for qvec in query_vectors:
        ranked_lists.append(dense_search(db, doc_id, qvec, dense_k))
    ranked_lists.append(keyword_search(db, doc_id, query_text, sparse_k))

    fused = reciprocal_rank_fusion(
        ranked_lists,
        k=rrf_k,
        toc_penalty=settings.RAG_TOC_PENALTY,
    )
    return fused[:candidate_k]


def search_chunks(
    db: Session,
    doc_id: uuid.UUID,
    qvec: list[float],
    k: int = 5,
) -> list[dict[str, Any]]:
    """Legacy single-vector dense search (kept for the eval baseline)."""
    return dense_search(db, doc_id, qvec, k)


def page_label(chunk: dict[str, Any]) -> str:
    """'page 3', or 'pages 3-4' for a chunk that spans a page break."""
    start = chunk["page_number"]
    end = chunk.get("page_end") or start
    return f"page {start}" if end == start else f"pages {start}-{end}"


def build_prompt(question: str, chunks: list[dict[str, Any]]) -> str:
    """
    Build a strict grounding prompt with [Chunk N] markers.

    Instructs the model to refuse when the answer is not in the chunks.
    """
    if not chunks:
        context = "(No relevant chunks were retrieved.)"
    else:
        parts: list[str] = []
        for chunk in chunks:
            idx = chunk["chunk_index"]
            text_body = chunk["chunk_text"]
            parts.append(f"[Chunk {idx}] ({page_label(chunk)}):\n{text_body}")
        context = "\n\n".join(parts)

    return (
        "You are a document Q&A assistant. Answer ONLY using the context chunks "
        "below. Do not use outside knowledge.\n"
        "When you use information from a chunk, cite it as [Chunk N] where N is "
        "the chunk_index shown in the marker.\n"
        f'If the answer is not contained in the chunks, reply exactly with: '
        f'"{REFUSAL_MESSAGE}"\n\n'
        f"Context:\n{context}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )
