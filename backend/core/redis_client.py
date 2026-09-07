"""
Redis helpers for Day 6: rate limit, answer cache, embedding cache.

Uses Upstash (or any Redis) via REDIS_URL. Ownership checks stay in the route —
never read caches before confirming document ownership.

REDIS_URL is re-read from the repo-root .env on each connect attempt so saving
.env does not require hunting a stale Settings cache (uvicorn only auto-reloads
on .py changes).
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import UTC, datetime
from typing import Any

import redis
from dotenv import load_dotenv

from core.config import _ENV_FILE, settings

_client: redis.Redis | None = None
_client_url: str | None = None


class RateLimitExceeded(Exception):
    """Raised when the user exceeds RATE_LIMIT_PER_HOUR asks in the current hour."""


def normalize_question(question: str) -> str:
    """Normalize before hashing so trivial whitespace/case variants share a cache key."""
    return question.strip().lower()


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _resolve_redis_url() -> str:
    """
    Prefer a live read of repo-root .env, then process env, then Settings.

    Upstash REST vars are not valid for redis-py — only rediss:// / redis:// URLs.
    """
    # override=True so a newly saved .env wins over an empty value loaded at startup
    load_dotenv(_ENV_FILE, override=True, encoding="utf-8")

    candidates = [
        os.getenv("REDIS_URL", ""),
        os.getenv("UPSTASH_REDIS_URL", ""),
        settings.REDIS_URL or "",
    ]
    for raw in candidates:
        url = (raw or "").strip().strip('"').strip("'")
        if url:
            return url
    return ""


def get_client() -> redis.Redis:
    """Lazy Redis client; fails clearly if REDIS_URL is missing."""
    global _client, _client_url

    url = _resolve_redis_url()
    if not url:
        raise RuntimeError(
            "REDIS_URL is empty. Set it in the repo-root .env (same line, no quotes needed):\n"
            f"  {_ENV_FILE.resolve()}\n"
            "Use the Upstash Redis URL starting with rediss:// (not the REST API URL).\n"
            "Save the file, then retry — or restart uvicorn if it still fails."
        )

    if not (url.startswith("redis://") or url.startswith("rediss://")):
        raise RuntimeError(
            "REDIS_URL must start with rediss:// or redis://. "
            "You may have pasted the Upstash REST URL instead of the Redis URL."
        )

    # Reconnect if the URL changed since last connect
    if _client is None or _client_url != url:
        _client = redis.from_url(url, decode_responses=True)
        _client_url = url
    return _client


def enforce_rate_limit(user_id: uuid.UUID) -> None:
    """
    INCR ratelimit:{user_id}:{YYYYMMDDHH}; EXPIRE on first hit; raise if over limit.
    """
    client = get_client()
    hour_bucket = datetime.now(UTC).strftime("%Y%m%d%H")
    key = f"ratelimit:{user_id}:{hour_bucket}"
    count = int(client.incr(key))
    if count == 1:
        client.expire(key, 3600)
    if count > settings.RATE_LIMIT_PER_HOUR:
        raise RateLimitExceeded(
            f"Rate limit exceeded ({settings.RATE_LIMIT_PER_HOUR} asks per hour)"
        )


def _answer_key(doc_id: uuid.UUID, question: str) -> str:
    # Pipeline version is part of the key so a retrieval change invalidates old answers.
    version = settings.RAG_PIPELINE_VERSION
    return f"answer:v{version}:{doc_id}:{sha256_hex(normalize_question(question))}"


def _embed_key(question: str) -> str:
    return f"embed:{sha256_hex(normalize_question(question))}"


def get_answer_cache(doc_id: uuid.UUID, question: str) -> dict[str, Any] | None:
    """Return cached {answer, sources} or None."""
    raw = get_client().get(_answer_key(doc_id, question))
    if not raw:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict) or "answer" not in data or "sources" not in data:
        return None
    return data


def set_answer_cache(
    doc_id: uuid.UUID,
    question: str,
    answer: str,
    sources: list[dict[str, Any]],
) -> None:
    payload = json.dumps({"answer": answer, "sources": sources})
    get_client().setex(
        _answer_key(doc_id, question),
        settings.ANSWER_CACHE_TTL,
        payload,
    )


def get_embed_cache(question: str) -> list[float] | None:
    raw = get_client().get(_embed_key(question))
    if not raw:
        return None
    data = json.loads(raw)
    if not isinstance(data, list):
        return None
    return [float(x) for x in data]


def set_embed_cache(question: str, qvec: list[float]) -> None:
    get_client().setex(
        _embed_key(question),
        settings.EMBED_CACHE_TTL,
        json.dumps(qvec),
    )
