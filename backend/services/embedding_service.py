"""
Embedding helpers using SentenceTransformer (BGE-small, 384-dim).

The model is loaded once at module import so request/background paths do not
pay load cost on every call (model init is slow and memory-heavy).

BGE-style models are asymmetric: queries get an instruction prefix, passages do
not. Embeddings are L2-normalized so pgvector cosine distance (<=>) behaves well.
"""

from sentence_transformers import SentenceTransformer

from core.config import settings

# Load once per process — do not move inside embed_* functions.
model = SentenceTransformer(settings.EMBEDDING_MODEL_NAME)


def embed_many(texts: list[str], is_query: bool = False) -> list[list[float]]:
    """
    Batch-embed texts into 384-dim, L2-normalized vectors.

    Set is_query=True for search queries so the BGE instruction prefix is added.
    Passages (document chunks) must be embedded with is_query=False.
    """
    if not texts:
        return []

    prepared = texts
    if is_query and settings.EMBEDDING_QUERY_INSTRUCTION:
        prefix = settings.EMBEDDING_QUERY_INSTRUCTION
        prepared = [f"{prefix}{t}" for t in texts]

    encoded = model.encode(
        prepared,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    vectors = [row.tolist() for row in encoded]

    dim = len(vectors[0]) if vectors else 0
    if dim != settings.EMBEDDING_DIM:
        raise ValueError(
            f"Embedding dim {dim} != configured EMBEDDING_DIM={settings.EMBEDDING_DIM}"
        )
    return vectors


def embed_query(text: str) -> list[float]:
    """Embed a single search query (adds the instruction prefix)."""
    return embed_many([text], is_query=True)[0]


def embed_queries(texts: list[str]) -> list[list[float]]:
    """Embed multiple search queries (adds the instruction prefix to each)."""
    return embed_many(texts, is_query=True)


def embed_text(text: str) -> list[float]:
    """
    Backward-compatible single-string embed.

    Treated as a query, since callers historically used this for questions.
    """
    return embed_query(text)
