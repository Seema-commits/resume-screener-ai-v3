"""
Security rules for roles, logins and scan visibility.

    pip install pytest
    pytest tests/

Uses DATABASE_URL if set (point it at a throwaway database - every
test wipes it), otherwise a temporary SQLite file.
"""

import pytest

from conftest import PASSWORD, make_world
from app.auth.permissions import (
    ACTIONS, HR_EXECUTIVE, HR_MANAGER, SUPERADMIN, can_manage, has_permission)
from app.database.db import SessionLocal
from app.database.init_db import init_db
from app.database.models import AgentLog, User
from app.services import auth_service, scan_service
from app.services.auth_service import AuthError


def fake_result(name):
    return {
        "shortlisted_candidates": [{"candidate_name": name, "score": 80,
                                    "decision": "Advance", "email": "c@x.com"}],
        "rejected_candidates": [],
        "parsed_profiles": [{"candidate_name": name, "skills": ["Python"]}],
        "criteria_weights": {"Skills": 40},
        "matched_weight_signals": [],
    }


# ---------------------------------------------------
# Permission table
# ---------------------------------------------------

def test_role_permissions():
    admin, manager, exec_a1, *_ = make_world()

    assert all(has_permission(admin, a) for a in ACTIONS)
    assert {a for a in ACTIONS if has_permission(manager, a)} == {
        "run_scan", "view_own_scans", "view_team_scans", "manage_users",
        "manage_org_keys"}
    assert {a for a in ACTIONS if has_permission(exec_a1, a)} == {
        "run_scan", "view_own_scans"}
    assert not has_permission(None, "run_scan")
    assert not has_permission(admin, "not_a_real_action")


def test_who_can_manage_whom():
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()

    assert can_manage(manager, HR_EXECUTIVE, org["Org A"])
    assert not can_manage(manager, HR_EXECUTIVE, org["Org B"])
    assert not can_manage(manager, HR_MANAGER, org["Org A"])
    assert not can_manage(manager, SUPERADMIN, org["Org A"])
    assert not can_manage(exec_a1, HR_EXECUTIVE, org["Org A"])
    assert can_manage(admin, HR_MANAGER, org["Org B"])
    assert not can_manage(admin, SUPERADMIN, org["Org A"])
    assert not can_manage(manager, HR_MANAGER, org["Org A"], manager.id)


def test_manager_cannot_create_outside_her_limits():
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()

    with pytest.raises(AuthError):
        auth_service.create_user(manager, org["Org A"], "M2", "m2@a.com", HR_MANAGER)
    with pytest.raises(AuthError):
        auth_service.create_user(manager, org["Org B"], "E", "x@b.com", HR_EXECUTIVE)
    with pytest.raises(AuthError):
        auth_service.create_user(exec_a1, org["Org A"], "E", "y@a.com", HR_EXECUTIVE)
    with pytest.raises(AuthError):
        auth_service.set_active(manager, exec_b.id, False)   # other org
    with pytest.raises(AuthError):
        auth_service.create_org(manager, "Org C")


# ---------------------------------------------------
# Passwords and login
# ---------------------------------------------------

def test_temp_password_forces_change_and_is_hashed():
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()

    temp = auth_service.create_user(manager, org["Org A"], "New", "new@a.com",
                                    HR_EXECUTIVE)
    user = auth_service.authenticate("new@a.com", temp)
    assert user.must_change_password

    with SessionLocal() as db:
        stored = db.get(User, user.id).password_hash
    assert stored != temp and stored.startswith("$2")    # bcrypt

    with pytest.raises(AuthError):                      # too short
        auth_service.change_password(user.id, temp, "short")
    auth_service.change_password(user.id, temp, PASSWORD)
    assert not auth_service.authenticate("new@a.com", PASSWORD).must_change_password
    with pytest.raises(AuthError):                      # temp no longer works
        auth_service.authenticate("new@a.com", temp)


def test_lockout_after_five_failures_and_unlock():
    admin, manager, exec_a1, *_ = make_world()

    for _ in range(4):
        with pytest.raises(AuthError, match="Invalid"):
            auth_service.authenticate("e1@a.com", "wrong-password")
    with pytest.raises(AuthError, match="locked"):
        auth_service.authenticate("e1@a.com", "wrong-password")

    with pytest.raises(AuthError, match="locked"):       # even the right one
        auth_service.authenticate("e1@a.com", PASSWORD)
    assert auth_service.load_user(exec_a1.id) is None     # logged out

    temp = auth_service.reset_password(manager, exec_a1.id)
    assert auth_service.authenticate("e1@a.com", temp).must_change_password


def test_deactivated_user_cannot_log_in_but_history_stays():
    admin, manager, exec_a1, *_ = make_world()
    scan_id = scan_service.save_scan(exec_a1, None, "JD", fake_result("Ann"))

    auth_service.set_active(manager, exec_a1.id, False)

    with pytest.raises(AuthError, match="deactivated"):
        auth_service.authenticate("e1@a.com", PASSWORD)
    assert auth_service.load_user(exec_a1.id) is None
    assert scan_service.load_scan(manager, scan_id) is not None


def test_unknown_email_gets_generic_message():
    make_world()
    with pytest.raises(AuthError, match="Invalid email or password"):
        auth_service.authenticate("nobody@x.com", PASSWORD)


# ---------------------------------------------------
# Scan visibility
# ---------------------------------------------------

def test_scan_visibility_by_role():
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    s1 = scan_service.save_scan(exec_a1, None, "Python JD", fake_result("A1"))
    s2 = scan_service.save_scan(exec_a2, None, "Java JD", fake_result("A2"))
    s3 = scan_service.save_scan(exec_b, None, "Go JD", fake_result("B"))

    ids = lambda viewer, **f: {s["id"] for s in scan_service.list_scans(viewer, **f)}

    assert ids(exec_a1) == {s1}
    assert ids(manager) == {s1, s2}
    assert ids(admin) == {s1, s2, s3}

    assert scan_service.load_scan(exec_a1, s2) is None     # teammate's scan
    assert scan_service.load_scan(manager, s3) is None     # other org
    assert scan_service.load_scan(admin, s3) is not None

    # Filters only narrow the scope, never widen it
    assert ids(manager, org_id=org["Org B"]) == set()
    assert ids(exec_a1, user_id=exec_a2.id) == set()
    assert ids(manager, user_id=exec_a2.id) == {s2}
    assert ids(manager, jd_query="python") == {s1}


def test_rerun_updates_same_scan():
    admin, manager, exec_a1, *_ = make_world()
    first = scan_service.save_scan(exec_a1, None, "JD", fake_result("A"))
    again = scan_service.save_scan(exec_a1, first, "JD v2", fake_result("B"))

    assert again == first
    scan = scan_service.load_scan(exec_a1, first)
    assert scan["jd_text"] == "JD v2"
    assert [c["candidate_name"] for c in scan["shortlisted_candidates"]] == ["B"]


# ---------------------------------------------------
# First Superadmin and logs
# ---------------------------------------------------

def test_bootstrap_creates_one_superadmin(monkeypatch):
    monkeypatch.setenv("BOOTSTRAP_SUPERADMIN_EMAIL", "Boss@X.com")
    monkeypatch.setenv("BOOTSTRAP_SUPERADMIN_PASSWORD", "temporary-pass-1")

    assert init_db() and init_db()                       # runs twice

    with SessionLocal() as db:
        admins = db.query(User).filter_by(role=SUPERADMIN).all()
    assert len(admins) == 1 and admins[0].email == "boss@x.com"
    assert auth_service.authenticate(
        "boss@x.com", "temporary-pass-1").must_change_password


def test_no_password_reaches_the_logs():
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    temp = auth_service.create_user(manager, org["Org A"], "T", "t@a.com",
                                    HR_EXECUTIVE)
    with pytest.raises(AuthError):
        auth_service.authenticate("t@a.com", "a-wrong-password")

    with SessionLocal() as db:
        db_logs = str([log.data for log in db.query(AgentLog).all()])

    for secret in (PASSWORD, temp, "a-wrong-password"):
        assert secret not in db_logs
