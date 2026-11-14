"""
The FastAPI backend: cookie sessions, CSRF, the forced password
change, every role boundary, uploads and the streamed scan.
"""

import io
import json
from datetime import datetime, timedelta

import pytest
from docx import Document
from fastapi.testclient import TestClient

from conftest import PASSWORD, make_world
from app.auth.permissions import HR_EXECUTIVE
from app.database.db import SessionLocal
from app.database.models import AgentLog, UserSession
from app.services import auth_service
from backend.deps import COOKIE_NAME, CSRF_HEADER
from backend.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "false")       # TestClient talks http
    with TestClient(app) as test_client:
        yield test_client


def login(client, email, password=PASSWORD):
    """Signs in; later requests carry the cookie and CSRF header."""
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    client.headers[CSRF_HEADER] = response.json()["csrf_token"]
    return response.json()


def docx_file(name, text):
    document = Document()
    for line in text.split("\n"):
        document.add_paragraph(line)
    data = io.BytesIO()
    document.save(data)
    return ("resumes", (name, data.getvalue(), "application/octet-stream"))


def screen(client, files, **form):
    response = client.post("/api/scans", files=files,
                           data={"jd_text": "Python backend engineer", **form})
    if not response.headers["content-type"].startswith("text/event-stream"):
        return response, []                            # rejected before screening
    events = [(block.split("\n")[0][7:], json.loads(block.split("\n")[1][6:]))
              for block in response.text.strip().split("\n\n") if block]
    return response, events


# ---------------------------------------------------
# Sessions
# ---------------------------------------------------

def test_login_sets_an_httponly_cookie_and_logout_ends_it(client):
    make_world()
    response = client.post("/api/auth/login",
                           json={"email": "e1@a.com", "password": PASSWORD})
    cookie = response.headers["set-cookie"]
    assert COOKIE_NAME in cookie and "HttpOnly" in cookie
    me = response.json()
    assert me["user"]["email"] == "e1@a.com"
    assert me["permissions"] == ["run_scan", "view_own_scans"]

    token = client.cookies.get(COOKIE_NAME)
    with SessionLocal() as db:                         # only a hash is stored
        assert db.query(UserSession).filter_by(token_hash=token).count() == 0
        assert db.query(UserSession).count() == 1

    client.headers[CSRF_HEADER] = me["csrf_token"]
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_wrong_password_is_401_with_a_generic_message(client):
    make_world()
    response = client.post("/api/auth/login",
                           json={"email": "e1@a.com", "password": "wrong-password"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."


def test_changes_need_the_csrf_token(client):
    admin, *_ = make_world()
    login(client, "admin@x.com")
    token = client.headers.pop(CSRF_HEADER)

    assert client.post("/api/orgs", json={"name": "Org C"}).status_code == 403
    client.headers[CSRF_HEADER] = token
    assert client.post("/api/orgs", json={"name": "Org C"}).status_code == 200


def test_temporary_password_must_be_changed_first(client):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    temp = auth_service.create_user(manager, org["Org A"], "New", "new@a.com", HR_EXECUTIVE)
    login(client, "new@a.com", temp)

    assert client.get("/api/scans").status_code == 403
    response = client.post("/api/auth/change-password",
                           json={"current_password": temp, "new_password": PASSWORD})
    assert response.json()["user"]["must_change_password"] is False
    assert client.get("/api/scans").status_code == 200


def test_idle_sessions_expire(client):
    make_world()
    login(client, "e1@a.com")
    with SessionLocal() as db:
        db.query(UserSession).update(
            {"last_seen_at": datetime.utcnow() - timedelta(hours=9)})
        db.commit()
    assert client.get("/api/auth/me").status_code == 401


def test_deactivating_a_user_ends_their_sessions(client):
    admin, manager, exec_a1, *_ = make_world()
    login(client, "e1@a.com")
    auth_service.set_active(manager, exec_a1.id, False)
    assert client.get("/api/auth/me").status_code == 401


# ---------------------------------------------------
# Role boundaries
# ---------------------------------------------------

@pytest.mark.parametrize("email,allowed", [
    ("e1@a.com", set()),
    ("mgr@a.com", {"/api/users", "/api/ai/catalog"}),
    ("admin@x.com", {"/api/users", "/api/ai/catalog", "/api/logs", "/api/logs/event-types"}),
])
def test_each_role_reaches_only_its_endpoints(client, email, allowed):
    make_world()
    login(client, email)
    for path in ["/api/users", "/api/ai/catalog", "/api/logs", "/api/logs/event-types"]:
        expected = 200 if path in allowed else 403
        assert client.get(path).status_code == expected, (email, path)


def test_manager_is_limited_to_her_org_and_executives(client):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    login(client, "mgr@a.com")

    emails = {u["email"] for u in client.get("/api/users").json()["items"]}
    assert "e@b.com" not in emails and "e1@a.com" in emails

    ok = client.post("/api/users", json={"name": "E3", "email": "e3@a.com",
                                         "role": "hr_executive"})
    assert ok.status_code == 200 and ok.json()["temp_password"]
    for body in ({"name": "M2", "email": "m2@a.com", "role": "hr_manager"},
                 {"name": "X", "email": "x@b.com", "role": "hr_executive",
                  "org_id": org["Org B"]}):
        assert client.post("/api/users", json=body).status_code == 400
    assert client.post(f"/api/users/{exec_b.id}/deactivate").status_code == 400
    assert client.get(f"/api/ai/orgs/{org['Org B']}").status_code == 403
    assert client.put(f"/api/ai/orgs/{org['Org A']}/models",
                      json={"model": "anthropic/claude-haiku-5-5"}).status_code == 400


def test_org_keys_are_write_only(client):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    login(client, "mgr@a.com")
    key = "sk-ant-org-a-secret-key-9876"

    assert client.put(f"/api/ai/orgs/{org['Org A']}/keys/anthropic",
                      json={"key": key}).status_code == 200
    settings = client.get(f"/api/ai/orgs/{org['Org A']}")
    assert settings.json()["keys"] == {"anthropic": "…9876"}
    assert key not in settings.text


# ---------------------------------------------------
# Scans
# ---------------------------------------------------

def test_scan_streams_progress_and_is_saved_and_scoped(client, fake_llm, monkeypatch):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-admin-test")
    from app.services import llm_settings_service
    llm_settings_service.set_key(manager, org["Org A"], "anthropic", "sk-ant-org-a-key-1")

    login(client, "e1@a.com")
    response, events = screen(client, [
        docx_file("Ann_Lee.docx", "Ann Lee\nann@example.com\nPython, 2018 - present"),
        docx_file("Bob_Ray.docx", "Bob Ray\nPython developer")])

    assert response.headers["content-type"].startswith("text/event-stream")
    names = [name for name, _ in events]
    assert names[0] == "progress" and names[-1] == "result"
    assert {"parse", "score"} <= {data["stage"] for name, data in events if name == "progress"}
    result = events[-1][1]
    shortlisted = result["result"]["shortlisted_candidates"]
    assert {c["candidate_name"] for c in shortlisted} == {"Ann Lee", "Bob Ray"}
    assert any(c["email"] == "ann@example.com" for c in shortlisted)

    # Adding a resume to the same scan only screens the new one
    calls_before = len(fake_llm)
    _, events = screen(client, [
        docx_file("Ann_Lee.docx", "Ann Lee\nann@example.com\nPython, 2018 - present"),
        docx_file("Bob_Ray.docx", "Bob Ray\nPython developer"),
        docx_file("Cat_Day.docx", "Cat Day\nPython developer")],
        scan_id=str(result["scan_id"]))
    assert events[-1][1]["result"]["run_stats"]["reused"] == 2
    assert len(fake_llm) - calls_before == 2           # one parse + one score call

    scan_id = result["scan_id"]
    assert client.get("/api/scans").json()["total"] == 1
    login(client, "mgr@a.com")
    assert client.get(f"/api/scans/{scan_id}").status_code == 200
    login(client, "e@b.com")
    assert client.get(f"/api/scans/{scan_id}").status_code == 404
    assert client.get("/api/scans").json()["total"] == 0

    with SessionLocal() as db:                         # logged with the user
        calls = db.query(AgentLog).filter_by(event_type="llm_call").all()
    assert calls and all(c.user_id == exec_a1.id for c in calls)


def test_scan_upload_limits(client):
    make_world()
    login(client, "e1@a.com")

    too_many = [docx_file(f"r{i}.docx", "x") for i in range(21)]
    assert screen(client, too_many)[0].status_code == 400
    assert screen(client, [("resumes", ("cv.txt", b"text", "text/plain"))])[0].status_code == 400
    big = [("resumes", ("big.pdf", b"0" * (5 * 1024 * 1024 + 1), "application/pdf"))]
    assert screen(client, big)[0].status_code == 413
    no_jd = client.post("/api/scans", files=[docx_file("a.docx", "x")], data={"jd_text": " "})
    assert no_jd.status_code == 400


def test_security_headers(client):
    response = client.get("/api/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"
