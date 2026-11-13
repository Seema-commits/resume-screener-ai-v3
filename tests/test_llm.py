"""
LLM routing, fallback, masking and org key isolation. LiteLLM is
replaced by a fake, so no real provider is called.
"""

from types import SimpleNamespace

import litellm
import pytest

from conftest import make_world
from app.database.db import SessionLocal
from app.database.models import AgentLog, OrgApiKey
from app.llm_config import DEFAULT_FALLBACK_MODEL, DEFAULT_MODEL
from app.services import llm_client, llm_settings_service
from app.services.auth_service import AuthError

ORG_A_KEY = "sk-ant-org-a-secret-key-1234"
ADMIN_KEY = "sk-ant-admin-secret-key-9999"


@pytest.fixture
def calls(monkeypatch):
    """Fake litellm.completion: records each call; a model listed in
    `calls.fail` raises that exception instead of answering."""

    record = SimpleNamespace(sent=[], fail={})

    def fake_completion(**kwargs):
        record.sent.append(kwargs)
        if kwargs["model"] in record.fail:
            raise record.fail[kwargs["model"]]
        return SimpleNamespace(
            choices=[SimpleNamespace(
                message=SimpleNamespace(content=f"answer from {kwargs['model']}"),
                finish_reason="stop")],
            usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))

    monkeypatch.setattr(llm_client.litellm, "completion", fake_completion)
    monkeypatch.setenv("ANTHROPIC_API_KEY", ADMIN_KEY)
    return record


def llm_logs():
    with SessionLocal() as db:
        return [log.data for log in db.query(AgentLog).filter_by(
            event_type="llm_call").order_by(AgentLog.id).all()]


def test_org_uses_its_own_key_and_the_default_model(calls):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    llm_settings_service.set_key(manager, org["Org A"], "anthropic", ORG_A_KEY)

    answer = llm_client.call_ai("hello", "system", org_id=org["Org A"])

    sent = calls.sent[-1]
    assert answer == f"answer from {DEFAULT_MODEL}"
    assert sent["model"] == DEFAULT_MODEL and sent["api_key"] == ORG_A_KEY
    assert sent["output_config"] == {"effort": "low"}       # same as before
    assert sent["messages"][0] == {"role": "system", "content": "system"}


def test_org_never_uses_another_orgs_or_the_admin_key(calls):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    llm_settings_service.set_key(manager, org["Org A"], "anthropic", ORG_A_KEY)

    with pytest.raises(RuntimeError, match="no anthropic key"):
        llm_client.call_ai("hello", org_id=org["Org B"])
    assert calls.sent == []                                  # nothing sent


def test_admin_org_uses_the_key_in_secrets(calls):
    admin, *_ = make_world()
    llm_client.call_ai("hello", org_id=admin.org_id)
    assert calls.sent[-1]["api_key"] == ADMIN_KEY


def test_falls_back_on_rate_limit_and_logs_which_model_answered(calls):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    llm_settings_service.set_key(manager, org["Org A"], "anthropic", ORG_A_KEY)
    calls.fail[DEFAULT_MODEL] = litellm.RateLimitError(
        message="slow down", llm_provider="anthropic", model=DEFAULT_MODEL)

    answer = llm_client.call_ai("hello", org_id=org["Org A"])

    assert answer == f"answer from {DEFAULT_FALLBACK_MODEL}"
    first, second = llm_logs()[-2:]
    assert (first["ok"], first["error"]) == (False, "RateLimitError")
    assert (second["ok"], second["fallback_used"], second["model"]) == (
        True, True, DEFAULT_FALLBACK_MODEL)


def test_custom_model_without_key_falls_back(calls):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    llm_settings_service.set_key(manager, org["Org A"], "anthropic", ORG_A_KEY)
    llm_settings_service.set_models(
        admin, org["Org A"], "groq/llama-3.3-70b-versatile", DEFAULT_FALLBACK_MODEL)

    assert llm_client.call_ai("hello", org_id=org["Org A"]) == (
        f"answer from {DEFAULT_FALLBACK_MODEL}")
    assert [c["model"] for c in calls.sent] == [DEFAULT_FALLBACK_MODEL]


def test_contact_details_are_masked_before_any_provider(calls):
    admin, *_ = make_world()
    llm_client.call_ai("Reach me at jane.doe@example.com or +971 50 123 4567, "
                       "linkedin.com/in/jane", org_id=admin.org_id)

    sent = calls.sent[-1]["messages"][-1]["content"]
    assert "jane.doe@example.com" not in sent and "+971" not in sent
    assert "[EMAIL]" in sent and "[PHONE]" in sent and "[PROFILE_URL]" in sent


def test_provider_errors_never_leak_keys(calls):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    llm_settings_service.set_key(manager, org["Org A"], "anthropic", ORG_A_KEY)
    for model in (DEFAULT_MODEL, DEFAULT_FALLBACK_MODEL):
        calls.fail[model] = litellm.AuthenticationError(
            message=f"invalid key {ORG_A_KEY}", llm_provider="anthropic", model=model)

    with pytest.raises(RuntimeError) as error:
        llm_client.call_ai("hello", org_id=org["Org A"])

    assert ORG_A_KEY not in str(error.value)
    assert ORG_A_KEY not in str(llm_logs())


def test_keys_are_encrypted_write_only_and_permission_checked(calls):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    llm_settings_service.set_key(manager, org["Org A"], "anthropic", ORG_A_KEY)

    with SessionLocal() as db:
        stored = db.query(OrgApiKey).one()
        all_logs = str([log.data for log in db.query(AgentLog).all()])
    assert ORG_A_KEY not in stored.encrypted_key and ORG_A_KEY not in all_logs
    assert llm_settings_service.key_status(manager, org["Org A"]) == {
        "anthropic": "…1234"}

    with pytest.raises(AuthError):                     # other org
        llm_settings_service.set_key(manager, org["Org B"], "anthropic", "sk-x-12345678")
    with pytest.raises(AuthError):                     # executives can't
        llm_settings_service.set_key(exec_a1, org["Org A"], "anthropic", "sk-x-12345678")
    with pytest.raises(AuthError):                     # only the Superadmin picks models
        llm_settings_service.set_models(manager, org["Org A"], DEFAULT_MODEL, None)
    assert llm_settings_service.key_status(exec_a1, org["Org A"]) == {}


def test_changed_encryption_secret_fails_safely(calls, monkeypatch):
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    llm_settings_service.set_key(manager, org["Org A"], "anthropic", ORG_A_KEY)

    monkeypatch.setenv("KEY_ENCRYPTION_SECRET", "a-different-secret-0123456789-abcdef")

    assert llm_settings_service.get_api_key(org["Org A"], "anthropic") is None
    with pytest.raises(RuntimeError, match="no anthropic key"):
        llm_client.call_ai("hello", org_id=org["Org A"])
