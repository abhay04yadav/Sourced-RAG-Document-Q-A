"""Anthropic Claude helpers: grounded answers + query rewriting."""

from __future__ import annotations

from anthropic import Anthropic

from core.config import settings

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    """Lazy Client so missing keys fail at ask-time, not import-time."""
    global _client
    if not settings.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is empty. Set it in the repo-root .env "
            "(https://console.anthropic.com/settings/keys)."
        )
    if _client is None:
        _client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    return _client


def _complete(prompt: str, max_tokens: int) -> str:
    """Single-turn Claude completion returning concatenated text blocks."""
    client = _get_client()
    message = client.messages.create(
        model=settings.ANTHROPIC_MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    parts: list[str] = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts).strip()


def generate_answer(prompt: str) -> str:
    """Call Claude with the grounded prompt; return plain text."""
    answer = _complete(prompt, max_tokens=2048)
    if not answer:
        raise RuntimeError("Anthropic returned an empty response")
    return answer


def rewrite_queries(question: str, n: int | None = None) -> list[str]:
    """
    Produce alternate search phrasings to widen semantic recall.

    Returns [original, *alternates]. Best-effort: on any failure (or n<=0) it
    returns just [original] so retrieval still runs.
    """
    n = n if n is not None else settings.RAG_QUERY_REWRITES
    if n <= 0:
        return [question]

    prompt = (
        "Rewrite the user's question into "
        f"{n} alternative search queries that could match relevant passages in a "
        "document, using synonyms and related concepts. Return ONLY the queries, "
        "one per line, with no numbering, quotes, or extra text.\n\n"
        f"Question: {question}"
    )

    try:
        raw = _complete(prompt, max_tokens=256)
    except Exception:
        return [question]

    alternates: list[str] = []
    for line in raw.splitlines():
        cleaned = line.strip().lstrip("-*0123456789. )").strip().strip('"').strip()
        if cleaned and cleaned.lower() != question.strip().lower():
            alternates.append(cleaned)

    # Dedupe while preserving order; cap at n alternates.
    seen: set[str] = set()
    unique: list[str] = []
    for q in alternates:
        key = q.lower()
        if key not in seen:
            seen.add(key)
            unique.append(q)
        if len(unique) >= n:
            break

    return [question, *unique]
