"""
The only place the app calls an LLM, through LiteLLM. Every agent
uses call_ai(); no other file imports litellm or names a provider
(model choices live in app/llm_config.py).

For each call:
1. contact details are masked (a safety net - the screening agent
   has already masked names, emails and phones),
2. the org's model is tried with the org's own key, then its
   fallback model if the first fails (rate limit, outage, bad key,
   unknown model...),
3. an "llm_call" log entry records which provider/model answered,
   tokens and time - never the prompt or the key,
4. when Langfuse is configured, the call is traced there too.
"""

import time

import litellm

from app.config import get_secret
from app.llm_config import PROVIDER_PARAMS, provider_of
from app.services import llm_settings_service
from app.services.logging_service import log_event
from app.utils.pii_masking import mask_contact_details

litellm.drop_params = True          # skip settings a model doesn't support
litellm.suppress_debug_info = True

# ---------------------------------------------------
# Tracing (Langfuse)
# ---------------------------------------------------
# On when LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are set (plus
# LANGFUSE_HOST for the US region). The keys are passed per call,
# never put in environment variables or logs. Prompts reaching
# LiteLLM are already masked; LANGFUSE_TRACE_CONTENT = "false" sends
# metadata only (model, tokens, cost, time - no prompt or answer).
# Adding or removing the keys takes effect after an app restart.

def _langfuse_credentials():
    public_key = get_secret("LANGFUSE_PUBLIC_KEY")
    secret_key = get_secret("LANGFUSE_SECRET_KEY")
    if not (public_key and secret_key):
        return None
    return {
        "langfuse_public_key": public_key,
        "langfuse_secret_key": secret_key,
        "langfuse_host": get_secret("LANGFUSE_HOST") or "https://cloud.langfuse.com",
    }


def tracing_host():
    """The Langfuse host when tracing is on, else None."""

    credentials = _langfuse_credentials()
    return credentials and credentials["langfuse_host"]


TRACING_CALLBACKS = ["langfuse"] if _langfuse_credentials() else []
litellm.success_callback = list(TRACING_CALLBACKS)
litellm.failure_callback = list(TRACING_CALLBACKS)


def _tracing_kwargs(org_id, user_id, stage, session_id):
    """Extra litellm.completion arguments that label the call in
    Langfuse - nothing when tracing is off."""

    credentials = _langfuse_credentials()
    if not credentials:
        return {}

    metadata_only = (
        (get_secret("LANGFUSE_TRACE_CONTENT") or "true").strip().lower() == "false")

    return {**credentials, "metadata": {
        "trace_name": f"talentlens.{stage}",
        "generation_name": stage,
        "session_id": session_id,
        "tags": [f"org:{org_id}", f"stage:{stage}"]
                + ([f"user:{user_id}"] if user_id else []),   # ids only, no emails
        "mask_input": metadata_only,
        "mask_output": metadata_only,
    }}

RETRIES_PER_MODEL = 2               # transient errors, before falling back


def _current_user():
    try:
        import streamlit as st
        return st.session_state.get("current_user")
    except Exception:
        return None


def _current_org_id():
    user = _current_user()
    return user.org_id if user else None


def current_models(org_id=None):
    """(model, fallback_model) call_ai() would use now for this org
    (default: the logged-in user's)."""

    return llm_settings_service.models_for_org(org_id or _current_org_id())


def _log(org_id, **data):
    log_event(session_id="llm", agent_name="llm_client",
              event_type="llm_call", data={"org_id": org_id, **data})


def call_ai(user_message, system_prompt=None, max_tokens=4000, org_id=None,
            only_model=None, stage="call", session_id=None):
    """
    Sends one prompt and returns the model's text answer. Uses the
    logged-in user's org unless org_id is given. only_model tries just
    that model (the Settings page's "Test model"). stage and
    session_id label the call in Langfuse (e.g. "parse", one screening
    session). Raises RuntimeError with a message safe to show if no
    configured model can answer.
    """

    org_id = org_id or _current_org_id()
    if org_id is None:
        raise RuntimeError("No organization - sign in first.")

    messages = ([{"role": "system", "content": system_prompt}]
                if system_prompt else [])
    messages.append(
        {"role": "user", "content": mask_contact_details(user_message)})

    primary, fallback = (
        (only_model, None) if only_model
        else llm_settings_service.models_for_org(org_id))
    failures = []
    user = _current_user()
    tracing = _tracing_kwargs(org_id, user and user.id, stage, session_id)

    for model in dict.fromkeys(m for m in (primary, fallback) if m):

        provider = provider_of(model)
        attempt = {"model": model, "provider": provider,
                   "fallback_used": model != primary}

        api_key = llm_settings_service.get_api_key(org_id, provider)
        if not api_key:
            failures.append(f"{model}: no {provider} key for this organization")
            _log(org_id, **attempt, ok=False, error="no_api_key")
            continue

        started = time.monotonic()
        try:
            response = litellm.completion(
                model=model, messages=messages, max_tokens=max_tokens,
                api_key=api_key, num_retries=RETRIES_PER_MODEL,
                **PROVIDER_PARAMS.get(provider, {}), **tracing)
        except Exception as e:
            # Error type only: provider messages can echo key fragments
            failures.append(f"{model}: {type(e).__name__}")
            _log(org_id, **attempt, ok=False, error=type(e).__name__,
                 ms=round((time.monotonic() - started) * 1000))
            continue

        choice = response.choices[0]
        text = choice.message.content or ""
        usage = getattr(response, "usage", None)
        _log(org_id, **attempt, ok=True,
             input_tokens=getattr(usage, "prompt_tokens", None),
             output_tokens=getattr(usage, "completion_tokens", None),
             ms=round((time.monotonic() - started) * 1000))

        if choice.finish_reason in ("content_filter", "refusal"):
            raise RuntimeError("The AI declined this request.")
        if not text and choice.finish_reason == "length":
            raise RuntimeError(
                "The AI used the whole max_tokens budget before answering "
                "- raise max_tokens for this call.")

        return text

    raise RuntimeError("No AI model could answer. " + "; ".join(failures))
