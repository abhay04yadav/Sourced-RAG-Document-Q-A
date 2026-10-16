"""Chat / RAG ask + session CRUD (Day 5–6)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from redis.exceptions import RedisError
from sqlalchemy.orm import Session, joinedload

from api.deps import get_current_user
from core.config import settings
from core.database import get_db
from core.redis_client import (
    RateLimitExceeded,
    enforce_rate_limit,
    get_answer_cache,
    get_embed_cache,
    set_answer_cache,
    set_embed_cache,
)
from models.chat import ChatMessage, ChatSession
from models.document import Document
from models.user import User
from schemas.chat import (
    AskRequest,
    AskResponse,
    SessionDetail,
    SessionOut,
    SourceOut,
)
from services.embedding_service import embed_queries, embed_text
from services.llm_service import generate_answer, rewrite_queries
from services.rag_service import build_prompt, hybrid_search
from services.rerank_service import expand_neighbors, rerank

router = APIRouter()


def _get_owned_session(db: Session, session_id: uuid.UUID, user: User) -> ChatSession:
    session = db.get(ChatSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )
    return session


def _persist_turn(
    db: Session,
    session: ChatSession,
    question: str,
    answer: str,
    sources: list[SourceOut],
) -> None:
    source_payload = [s.model_dump() for s in sources]
    db.add(
        ChatMessage(
            session_id=session.id,
            role="user",
            content=question,
            source_chunks=None,
        )
    )
    db.add(
        ChatMessage(
            session_id=session.id,
            role="assistant",
            content=answer,
            source_chunks=source_payload,
        )
    )
    db.commit()


@router.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AskResponse:
    """
    Ownership-first RAG ask with rate limit + Redis caches (Day 6).
    """
    # 1. Ownership / IDOR — before rate limit and cache
    doc = db.get(Document, body.document_id)
    if doc is None or doc.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # 2. Ready check
    if doc.status != "ready":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Document is not ready (status={doc.status})",
        )

    # 3. Rate limit
    try:
        enforce_rate_limit(current_user.id)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Redis unavailable: {exc}",
        ) from exc

    # 4. Resolve / create session
    if body.session_id is not None:
        session = db.get(ChatSession, body.session_id)
        if (
            session is None
            or session.user_id != current_user.id
            or session.document_id != body.document_id
        ):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Chat session not found",
            )
    else:
        session = ChatSession(
            user_id=current_user.id,
            document_id=body.document_id,
        )
        db.add(session)
        db.flush()

    # 5. Answer cache
    try:
        cached = get_answer_cache(body.document_id, body.question)
    except (RuntimeError, RedisError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    if cached is not None:
        sources = [SourceOut(**s) for s in cached["sources"]]
        _persist_turn(db, session, body.question, cached["answer"], sources)
        return AskResponse(
            session_id=session.id,
            answer=cached["answer"],
            sources=sources,
            cached=True,
        )

    # 6. Query rewrite (multi-query) — original question is embed-cached
    queries = rewrite_queries(body.question)

    qvec = get_embed_cache(body.question)
    if qvec is None:
        qvec = embed_text(body.question)
        set_embed_cache(body.question, qvec)

    query_vectors = [qvec]
    rewrites = queries[1:]
    if rewrites:
        query_vectors.extend(embed_queries(rewrites))

    # 7. Hybrid retrieve -> rerank -> neighbor expand -> LLM
    candidates = hybrid_search(
        db,
        body.document_id,
        query_vectors,
        body.question,
    )
    reranked = rerank(body.question, candidates)
    chunks = expand_neighbors(db, body.document_id, reranked)
    prompt = build_prompt(body.question, chunks)

    try:
        answer = generate_answer(prompt)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM request failed: {exc}",
        ) from exc

    sources = [
        SourceOut(
            chunk_index=int(c["chunk_index"]),
            page_number=int(c["page_number"]),
            page_end=int(c["page_end"]),
            chunk_text=str(c["chunk_text"]),
        )
        for c in chunks
    ]

    # 8. Answer cache set
    set_answer_cache(
        body.document_id,
        body.question,
        answer,
        [s.model_dump() for s in sources],
    )

    # 9. Persist + return
    _persist_turn(db, session, body.question, answer, sources)
    return AskResponse(
        session_id=session.id,
        answer=answer,
        sources=sources,
        cached=False,
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ChatSession]:
    """List chat sessions owned by the current user (newest first)."""
    return (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id)
        .order_by(ChatSession.created_at.desc())
        .all()
    )


@router.get("/sessions/{session_id}", response_model=SessionDetail)
def get_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ChatSession:
    """Return one owned session with its messages."""
    session = (
        db.query(ChatSession)
        .options(joinedload(ChatSession.messages))
        .filter(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
        .first()
    )
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Chat session not found",
        )
    return session


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete an owned chat session (messages cascade)."""
    session = _get_owned_session(db, session_id, current_user)
    db.delete(session)
    db.commit()
