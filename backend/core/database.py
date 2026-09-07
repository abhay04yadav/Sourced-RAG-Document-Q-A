"""
Database engine, session factory, and FastAPI dependency.

SQLAlchemy sessions are request-scoped: one session per HTTP request, closed
after the response so connections return to the pool cleanly.
"""

from collections.abc import Generator

from pgvector.psycopg2 import register_vector
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from core.config import settings

# pool_pre_ping=True: check connections before use so idle Supabase links
# that were closed by the server do not raise stale-connection errors.
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
)


@event.listens_for(engine, "connect")
def _register_vector(dbapi_connection, _connection_record) -> None:
    """Register pgvector adapters on every new DB-API connection."""
    register_vector(dbapi_connection)


# Factory for request-scoped sessions (autocommit/autoflush off = explicit control)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


class Base(DeclarativeBase):
    """
    Declarative base for all ORM models.

    Day 2+ models (User, Document, Chunk, …) inherit from this class so they
    share one metadata registry for create_all / migrations.
    """


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency that yields a database session for the current request.

    Uses `yield` (not `return`) so FastAPI can run the `finally` block after
    the response is sent — even if the route raises. That guarantees `db.close()`
    and prevents connection-pool leaks.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
