"""
TalentLens AI API - the backend for the React frontend.

    uvicorn backend.main:app --reload      # then open /docs

A thin layer over app/: every endpoint checks permission with
app/auth/permissions.py and calls the same services the Streamlit
app uses. Settings come from app/config.get_secret like everything
else (FRONTEND_ORIGINS, COOKIE_SECURE, COOKIE_SAMESITE, ...).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_secret
from app.database.init_db import init_db
from app.services.auth_service import AuthError
from backend.deps import CSRF_HEADER
from backend.routers import ai_settings, auth, logs, scans, users


@asynccontextmanager
async def lifespan(app):
    if not init_db():
        raise RuntimeError("The database isn't reachable - check DATABASE_URL.")
    yield


app = FastAPI(title="TalentLens AI API", version="1.0", lifespan=lifespan)

# Only the frontend's own address may call the API with cookies
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in (
        get_secret("FRONTEND_ORIGINS") or "http://localhost:5173").split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", CSRF_HEADER],
)


# Browser safety headers on every response; API data is never cached
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "frame-ancestors 'none'",
}


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(AuthError)
def auth_error(request, error):
    """Refusals from the services carry a message safe to show."""
    return JSONResponse(status_code=400, content={"detail": str(error)})


for module in (auth, scans, users, ai_settings, logs):
    app.include_router(module.router, prefix="/api")


@app.get("/api/health", tags=["health"])
def health():
    return {"ok": True}
