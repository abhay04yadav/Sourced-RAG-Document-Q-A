"""Pydantic schemas for user registration, responses, and tokens."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Registration body — password is hashed before storage."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(BaseModel):
    """Public user shape — never includes hashed_password."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    is_admin: bool
    created_at: datetime


class Token(BaseModel):
    """OAuth2-style access token response."""

    access_token: str
    token_type: str = "bearer"
