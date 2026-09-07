"""
Password hashing and JWT helpers.

Passwords are hashed with bcrypt (one-way). JWTs are signed with SECRET_KEY
(HS256) — the payload is readable but not forgeable without the secret.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Return True if plaintext matches the stored bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def _require_secret_key() -> str:
    """Fail fast if SECRET_KEY is missing — unsigned tokens must never ship."""
    if not settings.SECRET_KEY:
        raise RuntimeError(
            "SECRET_KEY is empty. Set a long random value in the repo-root .env."
        )
    return settings.SECRET_KEY


def create_access_token(
    subject: str,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Encode a JWT with `sub` (user id) and `exp`.

    Default lifetime comes from settings.ACCESS_TOKEN_EXPIRE_MINUTES.
    """
    expire = datetime.now(UTC) + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {"sub": subject, "exp": expire}
    return jwt.encode(payload, _require_secret_key(), algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.

    Raises jose.JWTError (and subclasses) when the token is expired, malformed,
    or the signature does not match SECRET_KEY.
    """
    return jwt.decode(
        token,
        _require_secret_key(),
        algorithms=[settings.ALGORITHM],
    )


# Re-export JWTError so callers can catch decode failures without importing jose.
__all__ = [
    "JWTError",
    "create_access_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
