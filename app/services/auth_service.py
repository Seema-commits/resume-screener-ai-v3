"""
Logins, passwords and user/org management.

Passwords are bcrypt-hashed and never stored, logged, shown or sent
to any LLM in plain text - except a newly generated temporary
password, which is returned once so the UI can show it once. Every
management action is checked with app/auth/permissions.py.
"""

import secrets
from dataclasses import dataclass
from datetime import datetime

import bcrypt

from app.auth.permissions import (
    SUPERADMIN,
    can_manage,
    has_permission,
)
from app.config import get_secret
from app.database.db import SessionLocal
from app.database.models import Organization, User
from app.services.logging_service import log_event

MAX_FAILED_LOGINS = 5
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_BYTES = 72          # bcrypt's limit
ADMIN_ORG_NAME = "TalentLens Admin"

INVALID_LOGIN = "Invalid email or password."
LOCKED = (
    "This account is locked after too many failed logins. Ask your "
    "HR Manager or the admin to unlock it."
)

# Checked against when the email doesn't exist, so a wrong email
# takes as long as a wrong password and doesn't reveal accounts.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt()).decode()


class AuthError(Exception):
    """A refusal with a message that is safe to show the user."""


@dataclass(frozen=True)
class CurrentUser:
    id: int
    org_id: int
    org_name: str
    name: str
    email: str
    role: str
    must_change_password: bool


# ---------------------------------------------------
# Helpers
# ---------------------------------------------------

def _hash(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _matches(password, password_hash):
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:      # e.g. longer than bcrypt's 72-byte limit
        return False


def _check_new_password(password):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
        )
    if len(password.encode()) > MAX_PASSWORD_BYTES:
        raise AuthError("Password is too long.")


def _email(value):
    return (value or "").strip().lower()


def _current(user, org):
    return CurrentUser(
        id=user.id, org_id=user.org_id, org_name=org.name,
        name=user.name, email=user.email, role=user.role,
        must_change_password=user.must_change_password,
    )


def _audit(event_type, **data):
    # Ids only - never passwords, and no emails in the logs.
    log_event(session_id="auth", agent_name="auth",
              event_type=event_type, data=data)


def _managed_user(db, actor, user_id):
    user = db.get(User, user_id)
    if user is None or not can_manage(actor, user.role, user.org_id, user.id):
        raise AuthError("You can't manage this user.")
    return user


def _new_user(db, org_id, name, email, role, password,
              must_change_password, created_by=None):
    name, email = (name or "").strip(), _email(email)

    if not name or "@" not in email:
        raise AuthError("Enter a name and a valid email.")
    if db.query(User).filter_by(email=email).first():
        raise AuthError("A user with this email already exists.")

    org = db.get(Organization, org_id)
    if org is None or not org.is_active:
        raise AuthError("That organization doesn't exist or is inactive.")

    user = User(
        org_id=org_id, name=name, email=email, role=role,
        password_hash=_hash(password),
        must_change_password=must_change_password,
        created_by=created_by,
    )
    db.add(user)
    db.commit()
    return user


# ---------------------------------------------------
# Login and passwords
# ---------------------------------------------------

def load_user(user_id):
    """The logged-in user, re-read on every page load so a user who
    was deactivated or locked mid-session is logged out at once."""

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not user.is_active or user.locked_at:
            return None
        org = db.get(Organization, user.org_id)
        if not org.is_active:
            return None
        return _current(user, org)


def authenticate(email, password):
    """Returns a CurrentUser, or raises AuthError. Five failures in
    a row lock the account."""

    with SessionLocal() as db:
        user = db.query(User).filter_by(email=_email(email)).first()

        if user is None:
            _matches(password, _DUMMY_HASH)
            _audit("login_failed", reason="unknown_account")
            raise AuthError(INVALID_LOGIN)

        if user.locked_at:
            _audit("login_failed", user_id=user.id, reason="locked")
            raise AuthError(LOCKED)

        if not _matches(password, user.password_hash):
            user.failed_login_count += 1
            if user.failed_login_count >= MAX_FAILED_LOGINS:
                user.locked_at = datetime.utcnow()
            db.commit()
            _audit("login_failed", user_id=user.id,
                   failed_count=user.failed_login_count,
                   locked=bool(user.locked_at))
            raise AuthError(LOCKED if user.locked_at else INVALID_LOGIN)

        org = db.get(Organization, user.org_id)
        if not user.is_active or not org.is_active:
            _audit("login_failed", user_id=user.id, reason="inactive")
            raise AuthError("This account is deactivated.")

        user.failed_login_count = 0
        user.last_login_at = datetime.utcnow()
        db.commit()
        _audit("login_success", user_id=user.id)
        return _current(user, org)


def change_password(user_id, current_password, new_password):
    _check_new_password(new_password)

    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user is None or not _matches(current_password, user.password_hash):
            raise AuthError("Current password is incorrect.")
        if current_password == new_password:
            raise AuthError("Choose a password different from the current one.")

        user.password_hash = _hash(new_password)
        user.must_change_password = False
        db.commit()
        _audit("password_changed", user_id=user_id)


# ---------------------------------------------------
# User and org management (all permission-checked)
# ---------------------------------------------------

def create_user(actor, org_id, name, email, role):
    """Returns the one-time temporary password for the new user."""

    if not can_manage(actor, role, org_id):
        raise AuthError("You can't create this kind of user here.")

    temp_password = secrets.token_urlsafe(12)
    with SessionLocal() as db:
        user = _new_user(db, org_id, name, email, role, temp_password,
                         must_change_password=True, created_by=actor.id)
    _audit("user_created", by=actor.id, user_id=user.id, role=role,
           org_id=org_id)
    return temp_password


def set_active(actor, user_id, active):
    """Deactivate (or reactivate) instead of deleting, so the user's
    scan history is kept."""

    with SessionLocal() as db:
        user = _managed_user(db, actor, user_id)
        user.is_active = active
        db.commit()
    _audit("user_activated" if active else "user_deactivated",
           by=actor.id, user_id=user_id)


def reset_password(actor, user_id):
    """Unlocks the account and returns a new one-time temporary
    password; the user must change it at next login."""

    temp_password = secrets.token_urlsafe(12)
    with SessionLocal() as db:
        user = _managed_user(db, actor, user_id)
        user.password_hash = _hash(temp_password)
        user.must_change_password = True
        user.failed_login_count = 0
        user.locked_at = None
        db.commit()
    _audit("password_reset", by=actor.id, user_id=user_id)
    return temp_password


def list_users(actor):
    """Users the actor may see: everyone for the Superadmin, the own
    org for an HR Manager, nobody for an HR Executive."""

    if not has_permission(actor, "manage_users"):
        return []

    with SessionLocal() as db:
        query = db.query(User, Organization).join(
            Organization, User.org_id == Organization.id
        )
        if not has_permission(actor, "manage_orgs"):
            query = query.filter(User.org_id == actor.org_id)

        names = dict(db.query(User.id, User.name).all())
        return [{
            "id": u.id, "name": u.name, "email": u.email, "role": u.role,
            "org_id": u.org_id, "org_name": o.name,
            "is_active": u.is_active,
            "status": ("Locked" if u.locked_at else
                       "Active" if u.is_active else "Inactive"),
            "created_by": names.get(u.created_by, ""),
            "last_login_at": u.last_login_at,
            "manageable": can_manage(actor, u.role, u.org_id, u.id),
        } for u, o in query.order_by(Organization.name, User.name).all()]


def list_orgs(actor):
    with SessionLocal() as db:
        query = db.query(Organization).order_by(Organization.name)
        if not has_permission(actor, "manage_orgs"):
            query = query.filter(Organization.id == actor.org_id)
        return [{"id": o.id, "name": o.name, "is_active": o.is_active}
                for o in query.all()]


def create_org(actor, name):
    name = (name or "").strip()
    if not has_permission(actor, "manage_orgs"):
        raise AuthError("You can't create organizations.")
    if not name:
        raise AuthError("Enter an organization name.")

    with SessionLocal() as db:
        if db.query(Organization).filter_by(name=name).first():
            raise AuthError("An organization with this name already exists.")
        org = Organization(name=name)
        db.add(org)
        db.commit()
    _audit("org_created", by=actor.id, org_id=org.id)


# ---------------------------------------------------
# First Superadmin
# ---------------------------------------------------

def create_superadmin(name, email, password, must_change_password=True):
    """Superadmins can't be created from the UI - only here, via
    bootstrap_superadmin() or app/scripts/create_superadmin.py."""

    _check_new_password(password)

    with SessionLocal() as db:
        org = db.query(Organization).filter_by(name=ADMIN_ORG_NAME).first()
        if org is None:
            org = Organization(name=ADMIN_ORG_NAME)
            db.add(org)
            db.commit()
        user = _new_user(db, org.id, name, email, SUPERADMIN, password,
                         must_change_password)
    _audit("superadmin_created", user_id=user.id)


def bootstrap_superadmin():
    """
    Creates the first Superadmin from the BOOTSTRAP_SUPERADMIN_*
    secrets, only while no Superadmin exists. The password there is
    temporary: it must be changed at first login, and the secrets
    should be removed afterwards.
    """

    email = get_secret("BOOTSTRAP_SUPERADMIN_EMAIL")
    password = get_secret("BOOTSTRAP_SUPERADMIN_PASSWORD")
    if not email or not password:
        return

    with SessionLocal() as db:
        if db.query(User).filter_by(role=SUPERADMIN).first():
            return

    try:
        create_superadmin(
            get_secret("BOOTSTRAP_SUPERADMIN_NAME") or "Superadmin",
            email, password, must_change_password=True,
        )
    except AuthError as e:
        print(f"[bootstrap_superadmin] Not created: {e}")
