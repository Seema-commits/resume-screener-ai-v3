"""Request bodies. Responses are plain dicts built from the services."""

from typing import Optional

from pydantic import BaseModel


class LoginIn(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserCreateIn(BaseModel):
    name: str
    email: str
    role: str
    org_id: Optional[int] = None        # defaults to the creator's org


class OrgCreateIn(BaseModel):
    name: str


class ModelsIn(BaseModel):
    model: str
    fallback_model: Optional[str] = None


class KeyIn(BaseModel):
    key: str                             # write-only: never returned or logged


class TestModelIn(BaseModel):
    model: str
