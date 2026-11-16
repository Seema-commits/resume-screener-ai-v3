"""
"Forgot password": one-time, expiring, hashed links; no way to learn
which emails have accounts; links always point at APP_URL; nothing
secret in the logs.
"""

import json
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from conftest import PASSWORD, make_world
from app.database.db import SessionLocal
from app.database.models import AgentLog, PasswordResetToken, User, UserSession
from app.services import auth_service, email_service
from app.services.auth_service import AuthError
from backend.main import app

NEW_PASSWORD = "a-brand-new-password"


@pytest.fixture
def mail(monkeypatch):
    """Email set up; captures what would be sent instead of sending."""
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("APP_URL", "https://talentlens.example.com/")
    sent = []
    monkeypatch.setattr(email_service, "send_password_reset",
                        lambda to, name, link, minutes: sent.append(
                            SimpleNamespace(to=to, name=name, link=link)))
    return sent


def token_from(link):
    return link.split("token=")[1]


def test_reset_flow_end_to_end(mail):
    _, manager, *_ = make_world()
    auth_service.request_password_reset("  MGR@a.com ", "/?reset_token=")

    assert [m.to for m in mail] == ["mgr@a.com"]
    link = mail[0].link
    assert link.startswith("https://talentlens.example.com/?reset_token=")
    token = token_from(link)

    with SessionLocal() as db:
        row = db.query(PasswordResetToken).one()
        assert token not in row.token_hash          # only a hash is stored
        assert row.expires_at - row.created_at == timedelta(minutes=30)

    auth_service.reset_password_with_token(token, NEW_PASSWORD)
    assert auth_service.authenticate("mgr@a.com", NEW_PASSWORD).id == manager.id
    with pytest.raises(AuthError):
        auth_service.authenticate("mgr@a.com", PASSWORD)

    # One use only
    with pytest.raises(AuthError, match="invalid or has expired"):
        auth_service.reset_password_with_token(token, "yet-another-password")


def test_unknown_or_inactive_accounts_get_nothing(mail):
    admin, _, exec_a1, *_ = make_world()
    auth_service.set_active(admin, exec_a1.id, False)

    auth_service.request_password_reset("nobody@x.com", "/?reset_token=")
    auth_service.request_password_reset("e1@a.com", "/?reset_token=")
    assert mail == []
    with SessionLocal() as db:
        assert db.query(PasswordResetToken).count() == 0


def test_expired_wrong_and_replaced_links_are_refused(mail):
    make_world()
    auth_service.request_password_reset("mgr@a.com", "/?reset_token=")
    first = token_from(mail[0].link)
    auth_service.request_password_reset("mgr@a.com", "/?reset_token=")
    second = token_from(mail[1].link)

    with pytest.raises(AuthError):        # replaced by the newer link
        auth_service.reset_password_with_token(first, NEW_PASSWORD)
    with pytest.raises(AuthError):
        auth_service.reset_password_with_token("made-up-token", NEW_PASSWORD)

    with SessionLocal() as db:
        row = db.query(PasswordResetToken).filter_by(used_at=None).one()
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
        db.commit()
    with pytest.raises(AuthError, match="expired"):
        auth_service.reset_password_with_token(second, NEW_PASSWORD)


def test_new_password_rules_apply(mail):
    make_world()
    auth_service.request_password_reset("mgr@a.com", "/?reset_token=")
    with pytest.raises(AuthError, match="at least 10"):
        auth_service.reset_password_with_token(token_from(mail[0].link), "short")


def test_three_emails_per_hour(mail):
    make_world()
    for _ in range(5):
        auth_service.request_password_reset("mgr@a.com", "/?reset_token=")
    assert len(mail) == auth_service.MAX_RESET_EMAILS_PER_HOUR


def test_reset_unlocks_and_ends_sessions(mail):
    _, manager, *_ = make_world()
    auth_service.create_session(manager)
    for _ in range(auth_service.MAX_FAILED_LOGINS):
        with pytest.raises(AuthError):
            auth_service.authenticate("mgr@a.com", "wrong-password")
    with pytest.raises(AuthError, match="locked"):
        auth_service.authenticate("mgr@a.com", PASSWORD)

    auth_service.request_password_reset("mgr@a.com", "/?reset_token=")
    auth_service.reset_password_with_token(token_from(mail[0].link), NEW_PASSWORD)

    assert auth_service.authenticate("mgr@a.com", NEW_PASSWORD)
    with SessionLocal() as db:
        assert db.query(UserSession).filter_by(user_id=manager.id).count() == 0


def test_not_set_up_says_so(monkeypatch):
    make_world()
    for name in ("SMTP_USER", "SMTP_PASSWORD", "APP_URL"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(AuthError, match="isn't set up"):
        auth_service.request_password_reset("mgr@a.com", "/?reset_token=")


def test_logs_hold_no_email_or_token(mail):
    make_world()
    auth_service.request_password_reset("mgr@a.com", "/?reset_token=")
    auth_service.request_password_reset("nobody@x.com", "/?reset_token=")
    token = token_from(mail[0].link)
    auth_service.reset_password_with_token(token, NEW_PASSWORD)

    with SessionLocal() as db:
        logged = json.dumps([log.data for log in db.query(AgentLog).filter(
            AgentLog.event_type.like("password_reset%")).all()])
    assert "mgr@a.com" not in logged and "nobody@x.com" not in logged
    assert token not in logged and NEW_PASSWORD not in logged


def test_cli_reset_sets_password_and_unlocks():
    make_world()
    with SessionLocal() as db:
        db.query(User).filter_by(email="admin@x.com").update(
            {"locked_at": datetime.utcnow()})
        db.commit()
    auth_service.set_password_from_cli("ADMIN@x.com", NEW_PASSWORD)
    assert auth_service.authenticate("admin@x.com", NEW_PASSWORD)
    with pytest.raises(AuthError):
        auth_service.set_password_from_cli("nobody@x.com", NEW_PASSWORD)


def test_email_is_plain_text_over_tls(monkeypatch):
    """The real sender: STARTTLS, login, one plain-text message."""
    monkeypatch.setenv("SMTP_USER", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self, context): calls.append(("starttls",))
        def login(self, user, password): calls.append(("login", user))
        def send_message(self, message): calls.append(("send", message))

    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)
    email_service._send("to@example.com", "Subject", "Body text")

    assert calls[:3] == [("connect", "smtp.gmail.com", 587), ("starttls",),
                         ("login", "sender@example.com")]
    message = calls[3][1]
    assert message["To"] == "to@example.com" and message.get_content_type() == "text/plain"

    with pytest.raises(ValueError):      # no header injection
        email_service._send("to@example.com\nBcc: evil@x.com", "S", "B")


# ---------- API ----------

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "false")
    with TestClient(app) as test_client:
        yield test_client


def test_api_same_answer_and_link_ignores_host_header(client, mail):
    make_world()
    known = client.post("/api/auth/forgot-password", json={"email": "mgr@a.com"},
                        headers={"Host": "evil.example.com"})
    unknown = client.post("/api/auth/forgot-password", json={"email": "nobody@x.com"})

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert len(mail) == 1
    assert mail[0].link.startswith("https://talentlens.example.com/reset-password#token=")
    assert "evil" not in mail[0].link

    token = mail[0].link.split("#token=")[1]
    bad = client.post("/api/auth/reset-password",
                      json={"token": "nope", "new_password": NEW_PASSWORD})
    assert bad.status_code == 400
    ok = client.post("/api/auth/reset-password",
                     json={"token": token, "new_password": NEW_PASSWORD})
    assert ok.status_code == 200
    assert client.post("/api/auth/login", json={
        "email": "mgr@a.com", "password": NEW_PASSWORD}).status_code == 200


def test_api_not_set_up(client, monkeypatch):
    make_world()
    monkeypatch.delenv("SMTP_USER", raising=False)
    response = client.post("/api/auth/forgot-password", json={"email": "mgr@a.com"})
    assert response.status_code == 503
    assert "isn't set up" in response.json()["detail"]
