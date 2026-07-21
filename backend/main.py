"""
FastAPI application entrypoint.

Run from the `backend/` directory:

    uvicorn main:app --reload --host 127.0.0.1 --port 8000
"""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from core.config import settings
from core.database import get_db

app = FastAPI(title=settings.APP_NAME)

# Restrict browser access to configured origins — never use "*" with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, str]:
    """
    Lightweight liveness probe used by Day 1 verify and load balancers.

    Does not touch the database — if this fails, the process itself is unhealthy.
    """
    return {"status": "ok"}


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    """
    Readiness probe: confirms the API can reach Postgres.

    Runs `SELECT 1` through the request-scoped session. Useful for Day 8 deploy
    checks; the plan's Day 1 contract remains `GET /` → `{"status":"ok"}`.
    """
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}
