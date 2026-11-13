from fastapi import APIRouter, Depends

from app.services import auth_service
from backend.deps import current_user, require
from backend.schemas import OrgCreateIn, UserCreateIn

router = APIRouter(tags=["users"])

PAGE_SIZE = 25

# Every action is re-checked in auth_service (can_manage), so these
# dependencies are the first gate, not the only one.


@router.get("/users")
def list_users(search: str = "", page: int = 1, user=Depends(require("manage_users"))):
    """Users the caller may see (all / own org), with name or email
    search, 25 per page."""

    search = search.strip().lower()
    users = [u for u in auth_service.list_users(user)
             if search in f"{u['name']} {u['email']}".lower()]
    page = max(page, 1)
    return {"total": len(users), "page": page, "page_size": PAGE_SIZE,
            "items": users[(page - 1) * PAGE_SIZE:page * PAGE_SIZE]}


@router.post("/users")
def create_user(body: UserCreateIn, user=Depends(require("manage_users"))):
    """Returns the one-time temporary password - show it once."""

    temp_password = auth_service.create_user(
        user, body.org_id or user.org_id, body.name, body.email, body.role)
    return {"temp_password": temp_password}


@router.post("/users/{user_id}/deactivate")
def deactivate_user(user_id: int, user=Depends(require("manage_users"))):
    auth_service.set_active(user, user_id, False)
    return {"ok": True}


@router.post("/users/{user_id}/reactivate")
def reactivate_user(user_id: int, user=Depends(require("manage_users"))):
    auth_service.set_active(user, user_id, True)
    return {"ok": True}


@router.post("/users/{user_id}/reset-password")
def reset_password(user_id: int, user=Depends(require("manage_users"))):
    """Unlocks the account; returns a new one-time temporary password."""
    return {"temp_password": auth_service.reset_password(user, user_id)}


@router.get("/orgs")
def list_orgs(user=Depends(current_user)):
    """All orgs for the Superadmin, otherwise the caller's own org."""
    return auth_service.list_orgs(user)


@router.post("/orgs")
def create_org(body: OrgCreateIn, user=Depends(require("manage_orgs"))):
    auth_service.create_org(user, body.name)
    return {"ok": True}
