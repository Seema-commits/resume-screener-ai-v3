"""
Shared test setup: a fresh database for every test (DATABASE_URL if
set - point it at a throwaway database - otherwise temp SQLite).
"""

import os
import tempfile

os.environ.setdefault(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db"))
os.environ.setdefault("KEY_ENCRYPTION_SECRET", "test-only-encryption-secret-0123456789")

import pytest

from app.auth.permissions import HR_EXECUTIVE, HR_MANAGER
from app.database.db import Base, engine
from app.database.init_db import init_db
from app.services import auth_service

PASSWORD = "correct-horse-battery"


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)          # log files go to a temp folder
    Base.metadata.drop_all(bind=engine)
    assert init_db()


def make_world():
    """Superadmin; org A with a manager and two executives; org B
    with one executive. Returns logged-in CurrentUsers."""

    auth_service.create_superadmin("Admin", "admin@x.com", PASSWORD, False)
    admin = auth_service.authenticate("admin@x.com", PASSWORD)
    auth_service.create_org(admin, "Org A")
    auth_service.create_org(admin, "Org B")
    org = {o["name"]: o["id"] for o in auth_service.list_orgs(admin)}

    def add(actor, org_id, email, role):
        temp = auth_service.create_user(actor, org_id, email, email, role)
        user = auth_service.authenticate(email, temp)
        auth_service.change_password(user.id, temp, PASSWORD)
        return auth_service.authenticate(email, PASSWORD)

    manager = add(admin, org["Org A"], "mgr@a.com", HR_MANAGER)
    exec_a1 = add(manager, org["Org A"], "e1@a.com", HR_EXECUTIVE)
    exec_a2 = add(manager, org["Org A"], "e2@a.com", HR_EXECUTIVE)
    exec_b = add(admin, org["Org B"], "e@b.com", HR_EXECUTIVE)
    return admin, manager, exec_a1, exec_a2, exec_b, org
