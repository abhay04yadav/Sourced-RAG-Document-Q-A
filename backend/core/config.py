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
        default="http://localhost:5173",
        description="Browser origins allowed to call the API",
    )

    APP_NAME: str = Field(
        default="Sourced RAG Document Q&A",
        description="Human-readable application title (shown in OpenAPI docs)",
    )

    # Placeholders for Day 2 JWT auth — loaded the same way as other secrets
    SECRET_KEY: str = Field(
        default="",
        description="JWT signing secret (set a long random value before Day 2)",
    )
    ALGORITHM: str = Field(
        default="HS256",
        description="JWT signing algorithm",
    )

    @property
    def origins(self) -> list[str]:
        """
        Parse ALLOWED_ORIGINS into a list for FastAPI CORSMiddleware.

        Empty segments are dropped so a trailing comma does not create a blank origin.
        """
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",") if origin.strip()]


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
