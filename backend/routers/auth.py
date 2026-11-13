from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.auth.permissions import ACTIONS, ROLE_LABELS, has_permission
from app.services import auth_service
from app.services.auth_service import AuthError
from backend.deps import COOKIE_NAME, cookie_settings, current_session
from backend.schemas import ChangePasswordIn, LoginIn

router = APIRouter(prefix="/auth", tags=["auth"])


def _me(user, csrf_token):
    """The signed-in user, what they may do (for the frontend's menu -
    every endpoint still checks), and the CSRF token to send back."""

    return {
        "user": {**asdict(user), "role_label": ROLE_LABELS[user.role]},
        "permissions": sorted(a for a in ACTIONS if has_permission(user, a)),
        "csrf_token": csrf_token,
    }


@router.post("/login")
def login(body: LoginIn, response: Response):
    try:
        user = auth_service.authenticate(body.email, body.password)
    except AuthError as e:
        raise HTTPException(401, str(e))

    token, csrf_token = auth_service.create_session(user)
    response.set_cookie(COOKIE_NAME, token, **cookie_settings())
    return _me(user, csrf_token)


@router.post("/logout")
def logout(request: Request, response: Response, session=Depends(current_session)):
    auth_service.end_session(request.cookies.get(COOKIE_NAME))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(session=Depends(current_session)):
    return _me(*session)


@router.post("/change-password")
def change_password(body: ChangePasswordIn, session=Depends(current_session)):
    user, csrf_token = session
    auth_service.change_password(user.id, body.current_password, body.new_password)
    return _me(auth_service.load_user(user.id), csrf_token)
