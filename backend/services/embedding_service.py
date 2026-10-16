"""
Embedding helpers using BGE-small (384-dim) via fastembed (ONNX Runtime).

fastembed runs the same BAAI/bge-small-en-v1.5 weights as sentence-transformers
(cosine 1.0000 against our stored vectors) without torch, so the API fits in a
free-tier container. No re-embedding was needed when switching.

The model is loaded once at module import so request/background paths do not
pay load cost on every call (model init is slow and memory-heavy).

BGE-style models are asymmetric: queries get an instruction prefix, passages do
not. Embeddings are L2-normalized so pgvector cosine distance (<=>) behaves well.
"""

from pathlib import Path

import numpy as np
from fastembed import TextEmbedding

from core.config import settings

_CACHE_DIR = settings.EMBEDDING_CACHE_DIR or str(
    Path(__file__).resolve().parents[1] / ".model_cache"
)

# Load once per process — do not move inside embed_* functions.
model = TextEmbedding(settings.EMBEDDING_MODEL_NAME, cache_dir=_CACHE_DIR)


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

    encoded = np.array(list(model.embed(prepared)), dtype=np.float32)
    encoded /= np.linalg.norm(encoded, axis=1, keepdims=True)
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
