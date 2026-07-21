# Project Notes

Bug log and day-by-day explainers. Keep this updated as you hit issues.

---

## Day 1 — Learn block (quick reference)

### ASGI vs WSGI
- **WSGI** (e.g. classic Flask): synchronous request/response. One worker handles one request at a time unless you add threads/processes.
- **ASGI** (FastAPI / Starlette): async-native. The event loop can await I/O (DB, HTTP to Gemini, Redis) without blocking the whole worker.
- FastAPI is ASGI; run it with **Uvicorn**, not a WSGI server like Gunicorn alone (Gunicorn can wrap Uvicorn workers in production).

### SQLAlchemy: Base, Session, engine
- **engine**: connection pool to Postgres (created once at startup).
- **Session**: unit of work for one request (or one background task). Do not share a session across concurrent requests.
- **Base**: declarative base class; all ORM models inherit from it so `Base.metadata.create_all()` / Alembic know the schema.
- Sessions are **per-request** via `get_db()` so connections return to the pool and you never leak open transactions.

### Pydantic v2 + BaseSettings
- Pydantic models validate request/response shapes at the API boundary.
- **BaseSettings** (pydantic-settings) loads typed config from environment / `.env` — 12-factor style. No secrets in source code.

### What pgvector is
- A PostgreSQL **extension** that adds a `vector` column type and distance operators (`<=>` cosine, `<->` L2, `<#>` inner product).
- Day 4 will store 384-dim embeddings and use an HNSW index; Day 1 only enables the extension.

### Why `get_db()` uses `yield` (Explain answer)
FastAPI treats a generator dependency as setup → inject → teardown. Code after `yield` runs after the response is sent (or after an error), so `db.close()` always runs. `return` would hand over the session with no guaranteed cleanup.

---

## Day 1 — Database + pgvector setup (manual)

**Preferred (matches the 14-day plan): Supabase**

1. Create a project at https://supabase.com
2. Project Settings → Database → copy the **URI** connection string
3. In repo-root `.env`, set (note the SQLAlchemy driver prefix):
   `DATABASE_URL=postgresql+psycopg2://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres`
4. SQL Editor → run `backend/scripts/enable_pgvector.sql`
5. Verify from the repo root:
   `backend\venv\Scripts\python.exe backend\scripts\verify_pgvector.py`
   Or in SQL: `SELECT * FROM pg_extension WHERE extname = 'vector';`

**Local alternative:** any Postgres with pgvector installed. Point `DATABASE_URL` at it
(default in `.env` is `127.0.0.1:5432/sourced`). Then run the same verify script.

> Note (2026-07-20): Docker Desktop on this machine hit an I/O error pulling
> `pgvector/pgvector:pg16`, so cloud Supabase (or a working local pgvector install)
> is required to fully green-check the extension query.

---

## Day 1 — Verify results (2026-07-20)

| Check | Result |
|---|---|
| `GET /` → `{"status":"ok"}` | Pass |
| `/docs` HTTP 200 | Pass |
| `.env` ignored by git | Pass (`gitignore:2:.env`) |
| `vector` extension row in Postgres | Pending — set real `DATABASE_URL` (Supabase), run `enable_pgvector.sql`, then `verify_pgvector.py` |

Server (from `backend/`): `.\venv\Scripts\uvicorn.exe main:app --reload --host 127.0.0.1 --port 8000`
