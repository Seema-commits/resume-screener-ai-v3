import os
import requests
import anthropic
from dotenv import load_dotenv

load_dotenv()


def _get_default_api_key():
    """
    Default key, in priority order:
    1. Streamlit secrets (used when deployed - set via the
       platform's Secrets UI, never committed to the repo)
    2. .env / environment variable (local development)
    """

    try:
        import streamlit as st
        if "ANTHROPIC_API_KEY" in st.secrets:
            return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        pass

    return os.getenv("ANTHROPIC_API_KEY")


DEFAULT_API_KEY = _get_default_api_key()

_client_cache = {}


def _get_client(api_key):
    """
    One Anthropic client per API key actually used (default key,
    or whatever a visitor entered in Settings), cached so we don't
    rebuild a client on every single call.
    """

    if not api_key:
        return None

    if api_key not in _client_cache:
        _client_cache[api_key] = anthropic.Anthropic(api_key=api_key)

    return _client_cache[api_key]


def call_local_model(user_message):
    """
    Local Ollama fallback. Only works when actually run on a
    machine with Ollama installed and running on localhost - this
    will NOT work once deployed to a hosted platform (no local
    LLM service available there). Fails gracefully if unreachable.
    """
    try:
        response = requests.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "llama3.1",
                "prompt": user_message,
                "stream": False
            },
            timeout=5
        )
        data = response.json()
        return data.get("response", "No response from local model.")
    except Exception:
        return None


MODEL = "claude-haiku-5-5"

# Haiku 5.5 thinks before answering (adaptive thinking is always
# on). "low" keeps thinking short for these structured extraction
# and scoring calls - the cheapest and fastest level.
EFFORT = "low"


def call_ai(
    user_message,
    system_prompt=None,
    max_tokens=4000,
    api_key=None
):
    """
    Calls Claude via the Anthropic API.

    api_key: if provided (e.g. a visitor's own key entered in the
    Settings page), used for this call only. Otherwise falls back
    to DEFAULT_API_KEY (yours, loaded from secrets/.env).

    Raises a clear, catchable error if no usable key/model is
    available, instead of silently trying a local model that
    won't exist once this app is deployed.
    """

    effective_key = api_key or DEFAULT_API_KEY

    client = _get_client(effective_key)

    if client:
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=max_tokens,
                output_config={"effort": EFFORT},
                system=system_prompt or "",
                messages=[{"role": "user", "content": user_message}]
            )
        except Exception as e:
            raise RuntimeError(
                f"Anthropic API call failed: {str(e)}"
            )

        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined this request.")

        # The response can start with thinking blocks, so collect
        # the text blocks rather than reading content[0].
        text = "".join(
            block.text for block in response.content
            if block.type == "text"
        )

        if not text and response.stop_reason == "max_tokens":
            raise RuntimeError(
                "Claude used the whole max_tokens budget before "
                "answering - raise max_tokens for this call."
            )

        return text

    # No API key at all - try local model as a last resort
    # (only meaningful for local development, not once deployed)
    local_result = call_local_model(
        (system_prompt + "\n\n" + user_message)
        if system_prompt else user_message
    )

    if local_result is not None:
        return local_result

    raise RuntimeError(
        "No Anthropic API key is configured, and the local model "
        "fallback is unreachable. Add a key in Settings, or "
        "configure ANTHROPIC_API_KEY."
    )