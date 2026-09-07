"""
FastAPI application entrypoint.

Run from the `backend/` directory:

    uvicorn main:app --reload --host 127.0.0.1 --port 8000
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.routes import auth, chat, documents
from core.config import settings
from core.database import Base, engine, get_db

# Import models so they register on Base.metadata before create_all.
import models  # noqa: F401

app = FastAPI(title=settings.APP_NAME)

# Restrict browser access to configured origins — never use "*" with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create tables that do not exist yet (users, documents, chunks, chat).
Base.metadata.create_all(bind=engine)

# Ensure upload root exists for Day 3 PDF storage.
settings.upload_path.mkdir(parents=True, exist_ok=True)

app.include_router(auth.router, prefix="/auth", tags=["auth"])
app.include_router(documents.router, prefix="/documents", tags=["documents"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])


@app.get("/")
def root() -> dict[str, str]:
    """
    Lightweight liveness probe used by Day 1 verify and load balancers.

    Does not touch the database — if this fails, the process itself is unhealthy.
    """
    return {"status": "ok"}


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    """
    Readiness probe: confirms the API can reach Postgres.

    Runs `SELECT 1` through the request-scoped session. Useful for Day 8 deploy
    checks; the plan's Day 1 contract remains `GET /` → `{"status":"ok"}`.
    """
    from api.routes.documents import _max_upload_bytes

    db.execute(text("SELECT 1"))
    return {
        "status": "ok",
        "database": "connected",
        "max_upload_bytes": _max_upload_bytes(),
    }
