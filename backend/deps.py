"""
Request checks shared by every endpoint: the signed-in user (from the
session cookie), CSRF on changes, the forced password change, and
require(action). Permission decisions come from
app/auth/permissions.py, as in the Streamlit app.
"""

import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool

from app.auth.permissions import has_permission
from app.config import get_secret
from app.context import set_current_user
from app.services import auth_service

COOKIE_NAME = "tl_session"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def cookie_settings():
    """COOKIE_SECURE=false only for local http development;
    COOKIE_SAMESITE=none when the frontend is on another site."""

    return {
        "httponly": True,
        "secure": (get_secret("COOKIE_SECURE") or "true").lower() != "false",
        "samesite": (get_secret("COOKIE_SAMESITE") or "lax").lower(),
        "max_age": int(auth_service.SESSION_MAX_AGE.total_seconds()),
        "path": "/",
    }


async def _session(request: Request, allow_password_change=False):
    found = await run_in_threadpool(
        auth_service.session_user, request.cookies.get(COOKIE_NAME))
    if found is None:
        raise HTTPException(401, "Not signed in.")

    user, csrf_token = found

    if request.method not in SAFE_METHODS and not secrets.compare_digest(
            request.headers.get(CSRF_HEADER, ""), csrf_token):
        raise HTTPException(403, "Missing or invalid CSRF token.")
    if user.must_change_password and not allow_password_change:
        raise HTTPException(403, "Change your temporary password first.")

    # Logging and the LLM client read the user from here
    set_current_user(user)
    return user, csrf_token


async def current_session(request: Request):
    """(user, csrf_token), also for a user who must still change a
    temporary password (only the auth endpoints use this)."""
    return await _session(request, allow_password_change=True)


async def current_user(request: Request):
    user, _ = await _session(request)
    return user


def require(action):
    """Dependency: the signed-in user, if their role allows `action`."""

    async def dependency(user=Depends(current_user)):
        if not has_permission(user, action):
            raise HTTPException(403, "You don't have permission for this.")
        return user

    return dependency
