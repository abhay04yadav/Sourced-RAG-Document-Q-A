"""
Verify that the pgvector extension is installed on DATABASE_URL.

Usage (from repo root, with .env configured):

    backend\\venv\\Scripts\\python.exe backend\\scripts\\verify_pgvector.py

Exits 0 on success, 1 on failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow importing core.config when run as a script from repo root or backend/
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import create_engine, text

from core.config import settings


def main() -> int:
    """Connect to Postgres and confirm the `vector` extension is present."""
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        # Ensure extension exists (idempotent — safe to re-run)
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
        row = conn.execute(
            text("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector'")
        ).fetchone()

    if row is None:
        print("FAIL: vector extension not found after CREATE EXTENSION")
        return 1

    print(f"OK: pgvector extension present (name={row[0]}, version={row[1]})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
