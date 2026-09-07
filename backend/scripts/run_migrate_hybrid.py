"""
Run the hybrid-search migration SQL against DATABASE_URL.

Usage (from repo root or backend/):

    backend\\venv\\Scripts\\python.exe backend\\scripts\\run_migrate_hybrid.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from sqlalchemy import text

from core.database import engine

SQL_PATH = Path(__file__).with_name("migrate_hybrid_search.sql")


def _statements(sql: str) -> list[str]:
    """Split SQL file into executable statements (skip comment-only lines)."""
    cleaned_lines: list[str] = []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        cleaned_lines.append(line)
    cleaned = "\n".join(cleaned_lines)
    return [part.strip() for part in cleaned.split(";") if part.strip()]


def main() -> None:
    sql = SQL_PATH.read_text(encoding="utf-8")
    with engine.begin() as conn:
        for stmt in _statements(sql):
            conn.execute(text(stmt))
    print("Hybrid-search migration applied:", SQL_PATH.name)


if __name__ == "__main__":
    main()
