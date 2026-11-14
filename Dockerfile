# TalentLens AI API (FastAPI) for Google Cloud Run.
# Secrets are never baked in: Cloud Run passes them as environment
# variables from Secret Manager (see DEPLOY.md).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY backend ./backend

# Run as a non-root user
RUN useradd --create-home --uid 10001 talentlens
USER talentlens

# Cloud Run sets $PORT; --proxy-headers trusts its load balancer
CMD exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'
