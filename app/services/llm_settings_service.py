"""
Per-org LLM settings:
- which models an org uses (chosen by the Superadmin; orgs without a
  choice use the defaults in app/llm_config.py), and
- the org's own provider keys, entered by its HR Manager or the
  Superadmin, stored encrypted with KEY_ENCRYPTION_SECRET and
  write-only: only the last 4 characters are ever shown.

The TalentLens Admin org uses the keys in Secrets instead. An org
never uses another org's keys, or the Superadmin's.
"""

import base64
import hashlib
import re
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken

from app.auth.permissions import can_manage_org, has_permission
from app.config import get_secret
from app.database.db import SessionLocal
from app.database.models import Organization, OrgApiKey, OrgLlmSetting
from app.llm_config import (
    DEFAULT_FALLBACK_MODEL, DEFAULT_MODEL, PROVIDER_KEY_SECRETS)
from app.services.auth_service import ADMIN_ORG_NAME, AuthError
from app.services.logging_service import log_event

_PROVIDER_RE = re.compile(r"^[a-z0-9_]+$")
_MODEL_RE = re.compile(r"^[a-z0-9_]+/\S+$")


MIN_SECRET_LENGTH = 32


def _fernet():
    """Encryption from KEY_ENCRYPTION_SECRET - any long random string
    (a password manager's 40+ character password is ideal). Changing
    it makes every stored org key unreadable, so keep a backup."""

    secret = get_secret("KEY_ENCRYPTION_SECRET") or ""
    if len(secret) < MIN_SECRET_LENGTH:
        raise AuthError(
            f"KEY_ENCRYPTION_SECRET is missing or shorter than "
            f"{MIN_SECRET_LENGTH} characters, so org keys can't be "
            f"stored or used. Add it to the app's secrets.")
    return Fernet(base64.urlsafe_b64encode(
        hashlib.sha256(secret.encode()).digest()))


def _audit(event_type, **data):
    # Never the key itself
    log_event(session_id="llm_settings", agent_name="llm_settings",
              event_type=event_type, data=data)


def is_admin_org(org_id):
    with SessionLocal() as db:
        org = db.get(Organization, org_id)
        return org is not None and org.name == ADMIN_ORG_NAME


# ---------------------------------------------------
# Models
# ---------------------------------------------------

def models_for_org(org_id):
    """(model, fallback_model) for this org."""

    with SessionLocal() as db:
        row = db.query(OrgLlmSetting).filter_by(org_id=org_id).first()

    if row is None:
        return DEFAULT_MODEL, DEFAULT_FALLBACK_MODEL

    return row.model, row.fallback_model


def set_models(actor, org_id, model, fallback_model):
    model, fallback_model = (model or "").strip(), (fallback_model or "").strip()

    if not has_permission(actor, "choose_llm_models"):
        raise AuthError("You can't change AI models.")
    if not _MODEL_RE.match(model) or (
            fallback_model and not _MODEL_RE.match(fallback_model)):
        raise AuthError('Models must look like "provider/model-name".')

    with SessionLocal() as db:
        row = db.query(OrgLlmSetting).filter_by(org_id=org_id).first()
        if row is None:
            row = OrgLlmSetting(org_id=org_id)
            db.add(row)
        row.model = model
        row.fallback_model = fallback_model or None
        row.updated_by = actor.id
        row.updated_at = datetime.utcnow()
        db.commit()

    _audit("llm_models_changed", by=actor.id, org_id=org_id,
           model=model, fallback_model=fallback_model or None)


# ---------------------------------------------------
# Keys
# ---------------------------------------------------

def _check_key_access(actor, org_id, provider=None):
    if not can_manage_org(actor, "manage_org_keys", org_id):
        raise AuthError("You can't manage AI keys for this organization.")
    if is_admin_org(org_id):
        raise AuthError("The admin organization uses the keys in Secrets.")
    if provider is not None and not _PROVIDER_RE.match(provider):
        raise AuthError("Unknown provider.")


def key_status(actor, org_id):
    """{provider: "…abcd"} for the org's stored keys - or, for the
    admin org, {provider: "Secrets"} for each key set in Secrets.
    Never returns a key."""

    if not can_manage_org(actor, "manage_org_keys", org_id):
        return {}

    if is_admin_org(org_id):
        return {p: "Secrets" for p, name in PROVIDER_KEY_SECRETS.items()
                if get_secret(name)}

    with SessionLocal() as db:
        return {k.provider: f"…{k.last4}" for k in
                db.query(OrgApiKey).filter_by(org_id=org_id).all()}


def set_key(actor, org_id, provider, key):
    provider, key = (provider or "").strip().lower(), (key or "").strip()
    _check_key_access(actor, org_id, provider)
    if len(key) < 8:
        raise AuthError("That doesn't look like an API key.")

    encrypted = _fernet().encrypt(key.encode()).decode()

    with SessionLocal() as db:
        row = db.query(OrgApiKey).filter_by(
            org_id=org_id, provider=provider).first()
        if row is None:
            row = OrgApiKey(org_id=org_id, provider=provider)
            db.add(row)
        row.encrypted_key = encrypted
        row.last4 = key[-4:]
        row.updated_by = actor.id
        row.updated_at = datetime.utcnow()
        db.commit()

    _audit("org_key_set", by=actor.id, org_id=org_id, provider=provider)


def remove_key(actor, org_id, provider):
    _check_key_access(actor, org_id, provider)

    with SessionLocal() as db:
        db.query(OrgApiKey).filter_by(
            org_id=org_id, provider=provider).delete()
        db.commit()

    _audit("org_key_removed", by=actor.id, org_id=org_id, provider=provider)


def get_api_key(org_id, provider):
    """The org's decrypted key for this provider, or None. Only for
    services/llm_client.py - never show, log or store the result."""

    if is_admin_org(org_id):
        name = PROVIDER_KEY_SECRETS.get(provider)
        return get_secret(name) if name else None

    with SessionLocal() as db:
        row = db.query(OrgApiKey).filter_by(
            org_id=org_id, provider=provider).first()

    if row is None:
        return None

    try:
        return _fernet().decrypt(row.encrypted_key.encode()).decode()
    except (InvalidToken, AuthError):
        return None    # e.g. KEY_ENCRYPTION_SECRET changed: re-enter the key
