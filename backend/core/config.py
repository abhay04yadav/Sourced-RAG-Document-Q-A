"""
Application settings loaded from environment variables / `.env`.

Uses pydantic-settings so config is typed, validated at startup, and never
hard-coded. Secrets stay out of source control (see `.env.example`).
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/core/config.py → parents[2] is the repository root
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"


class Settings(BaseSettings):
    """
    Central configuration for the API.

    Values are read from process env first, then from the repo-root `.env` file.
    Missing required fields cause startup to fail fast instead of mid-request.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Required: SQLAlchemy URL, e.g. postgresql+psycopg2://user:pass@host:5432/db
    DATABASE_URL: str = Field(
        ...,
        min_length=1,
        description="PostgreSQL connection string used by SQLAlchemy",
    )

    # Comma-separated list; parsed via the `origins` property for CORSMiddleware
    ALLOWED_ORIGINS: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        description="Browser origins allowed to call the API",
    )

    APP_NAME: str = Field(
        default="Sourced RAG Document Q&A",
        description="Human-readable application title (shown in OpenAPI docs)",
    )

    # JWT auth — loaded the same way as other secrets
    SECRET_KEY: str = Field(
        default="",
        description="JWT signing secret (set a long random value before Day 2)",
    )
    ALGORITHM: str = Field(
        default="HS256",
        description="JWT signing algorithm",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="Access token lifetime in minutes",
    )

    # Day 3 — PDF uploads + page-aware chunking
    UPLOAD_DIR: str = Field(
        default="uploads",
        description="Directory for stored PDFs (relative to repo root unless absolute)",
    )
    MAX_UPLOAD_BYTES: int = Field(
        default=20_971_520,
        description="Maximum upload size in bytes (default 20 MB)",
    )
    # Section-aware chunking (word windows across pages, within a section)
    CHUNK_SIZE: int = Field(
        default=800,
        description="Target words per chunk within a section",
    )
    CHUNK_OVERLAP: int = Field(
        default=100,
        description="Word overlap between consecutive chunks in the same section",
    )

    # Day 4 — embeddings (must match Vector(384) column)
    EMBEDDING_MODEL_NAME: str = Field(
        default="BAAI/bge-small-en-v1.5",
        description="SentenceTransformer model id (384-dim output)",
    )
    EMBEDDING_DIM: int = Field(
        default=384,
        description="Expected embedding dimensionality (must match Vector column)",
    )
    EMBEDDING_QUERY_INSTRUCTION: str = Field(
        default="Represent this sentence for searching relevant passages: ",
        description="Instruction prefix prepended to query text for BGE-style models",
    )

    # Day 5 — OpenAI LLM for RAG
    OPENAI_API_KEY: str = Field(
        default="",
        description="OpenAI API key",
    )
    OPENAI_MODEL: str = Field(
        default="gpt-4o-mini",
        description="OpenAI chat model id for grounded answers + query rewriting",
    )
    RAG_TOP_K: int = Field(
        default=5,
        description="Legacy single-vector top-k (kept for reference; pipeline uses the knobs below)",
    )

    # Standard retrieve -> fuse -> rerank pipeline knobs
    RAG_DENSE_K: int = Field(
        default=30,
        description="Dense (vector) candidates fetched per query embedding",
    )
    RAG_SPARSE_K: int = Field(
        default=30,
        description="Sparse (Postgres FTS) candidates fetched per question",
    )
    RAG_RRF_K: int = Field(
        default=60,
        description="Reciprocal Rank Fusion constant (score = sum 1/(k + rank))",
    )
    RAG_CANDIDATE_K: int = Field(
        default=40,
        description="Fused candidates passed into the cross-encoder reranker",
    )
    RAG_CONTEXT_K: int = Field(
        default=12,
        description="Reranked chunks kept as LLM context before neighbor expansion",
    )
    RAG_NEIGHBOR_WINDOW: int = Field(
        default=1,
        description="Adjacent chunk_index rows to pull around each kept chunk (0 disables)",
    )
    RAG_NEIGHBOR_CAP: int = Field(
        default=18,
        description="Hard cap on total chunks (context + neighbors) sent to the LLM",
    )
    RAG_TOC_PENALTY: float = Field(
        default=0.3,
        description="Multiplier applied to fused scores of table-of-contents chunks",
    )
    RAG_QUERY_REWRITES: int = Field(
        default=3,
        description="Number of alternate query phrasings requested from the LLM (0 disables)",
    )
    RERANKER_MODEL_NAME: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        description="CrossEncoder model id for retrieve-then-rerank",
    )
    RAG_PIPELINE_VERSION: int = Field(
        default=2,
        description="Bumped when retrieval changes; part of the answer-cache key to invalidate stale answers",
    )

    # Day 6 — Redis cache + rate limit (Upstash rediss:// URL)
    REDIS_URL: str = Field(
        default="",
        description="Redis connection URL (Upstash or local)",
    )
    RATE_LIMIT_PER_HOUR: int = Field(
        default=20,
        description="Max /chat/ask requests per user per hour",
    )
    ANSWER_CACHE_TTL: int = Field(
        default=3600,
        description="Answer cache TTL in seconds",
    )
    EMBED_CACHE_TTL: int = Field(
        default=86400,
        description="Question embedding cache TTL in seconds",
    )

    @property
    def origins(self) -> list[str]:
        """
        Parse ALLOWED_ORIGINS into a list for FastAPI CORSMiddleware.

        Empty segments are dropped so a trailing comma does not create a blank origin.
        """
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def upload_path(self) -> Path:
        """Absolute path to the upload directory (repo-root relative when UPLOAD_DIR is relative)."""
        path = Path(self.UPLOAD_DIR)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        return path


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings instance.

    Caching avoids re-reading the env file on every import/dependency injection.
    Call `get_settings.cache_clear()` in tests if you change env vars.
    """
    return Settings()


# Module-level singleton used by database.py and main.py
settings = get_settings()
