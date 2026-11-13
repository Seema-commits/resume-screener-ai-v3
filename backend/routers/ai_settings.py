from fastapi import APIRouter, Depends, HTTPException

from app.auth.permissions import can_manage_org, has_permission
from app.llm_config import (
    DEFAULT_FALLBACK_MODEL, DEFAULT_MODEL, FREE_TIER_PROVIDERS,
    FREE_TIER_WARNING, MODELS)
from app.services import llm_settings_service
from app.services.llm_client import call_ai, tracing_host
from backend.deps import current_user, require
from backend.schemas import KeyIn, ModelsIn, TestModelIn

router = APIRouter(prefix="/ai", tags=["ai settings"])


def _check_org_access(user, org_id):
    """Superadmin (any org) or the org's own HR Manager."""
    if not (has_permission(user, "choose_llm_models")
            or can_manage_org(user, "manage_org_keys", org_id)):
        raise HTTPException(403, "You can't view AI settings for this organization.")


@router.get("/catalog")
def catalog(user=Depends(current_user)):
    if not (has_permission(user, "choose_llm_models")
            or has_permission(user, "manage_org_keys")):
        raise HTTPException(403, "You don't have permission for this.")
    return {
        "models": MODELS,
        "default_model": DEFAULT_MODEL,
        "default_fallback_model": DEFAULT_FALLBACK_MODEL,
        "free_tier_providers": sorted(FREE_TIER_PROVIDERS),
        "free_tier_warning": FREE_TIER_WARNING,
        "tracing_host": tracing_host(),
    }


@router.get("/orgs/{org_id}")
def org_settings(org_id: int, user=Depends(current_user)):
    """The org's saved models and key status (never the keys)."""

    _check_org_access(user, org_id)
    model, fallback_model = llm_settings_service.models_for_org(org_id)
    return {
        "model": model,
        "fallback_model": fallback_model,
        "uses_secrets": llm_settings_service.is_admin_org(org_id),
        "keys": llm_settings_service.key_status(user, org_id),
    }


@router.put("/orgs/{org_id}/models")
def set_models(org_id: int, body: ModelsIn, user=Depends(current_user)):
    llm_settings_service.set_models(user, org_id, body.model, body.fallback_model)
    return {"ok": True}


@router.put("/orgs/{org_id}/keys/{provider}")
def set_key(org_id: int, provider: str, body: KeyIn, user=Depends(current_user)):
    llm_settings_service.set_key(user, org_id, provider, body.key)
    return {"ok": True}


@router.delete("/orgs/{org_id}/keys/{provider}")
def remove_key(org_id: int, provider: str, user=Depends(current_user)):
    llm_settings_service.remove_key(user, org_id, provider)
    return {"ok": True}


@router.post("/orgs/{org_id}/test")
def test_model(org_id: int, body: TestModelIn, user=Depends(require("choose_llm_models"))):
    """Sends a tiny prompt to one model with the org's key."""

    try:
        answer = call_ai("Reply with the single word OK.", org_id=org_id,
                         max_tokens=2000, only_model=body.model, stage="test")
        return {"ok": True, "answer": answer.strip()[:40]}
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
