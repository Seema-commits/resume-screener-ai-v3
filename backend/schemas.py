"""Request bodies. Responses are plain dicts built from the services."""

from typing import Optional

from pydantic import BaseModel, Field


class LoginIn(BaseModel):
    email: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class ForgotPasswordIn(BaseModel):
    email: str = Field(max_length=320)


class ResetPasswordIn(BaseModel):
    token: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


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
