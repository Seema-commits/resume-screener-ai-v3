import streamlit as st

from app.llm_config import (
    DEFAULT_FALLBACK_MODEL, DEFAULT_MODEL, FREE_TIER_PROVIDERS,
    FREE_TIER_WARNING, MODELS, label_of, provider_of)
from app.services import auth_service, llm_settings_service
from app.services.auth_service import AuthError
from app.services.llm_client import call_ai, tracing_host
from app.ui.auth_ui import require
from app.ui.llm_ui import render_org_keys

user = require("choose_llm_models")

st.title("🤖 AI Model Settings")
st.caption(
    f"Organizations without their own choice use "
    f"**{label_of(DEFAULT_MODEL)}**, falling back to "
    f"**{label_of(DEFAULT_FALLBACK_MODEL)}** (from config). API keys are "
    f"never shown here - only whether one is set.")

host = tracing_host()
st.caption(f"📈 Langfuse tracing: **ON** ({host})" if host else
           "📈 Langfuse tracing: **OFF** - add LANGFUSE_PUBLIC_KEY and "
           "LANGFUSE_SECRET_KEY to the secrets to turn it on.")

orgs = auth_service.list_orgs(user)
org = st.selectbox("Organization", orgs, format_func=lambda o: o["name"])
model, fallback = llm_settings_service.models_for_org(org["id"])

CUSTOM = "Custom LiteLLM model…"


def pick_model(label, current, key, allow_none=False):
    """Built-in models, plus any LiteLLM model typed in."""

    options = ([None] if allow_none else []) + list(MODELS) + [CUSTOM]
    index = options.index(current) if current in options else options.index(CUSTOM)
    choice = st.selectbox(
        label, options, index=index, key=key,
        format_func=lambda m: "None" if m is None else MODELS.get(m, m))

    if choice == CUSTOM:
        return st.text_input(
            f"{label} - LiteLLM name", key=f"{key}_custom",
            value=current if current not in MODELS else "",
            placeholder="e.g. groq/llama-3.3-70b-versatile")
    return choice


col1, col2 = st.columns(2)
with col1:
    new_model = pick_model("Model", model, f"model_{org['id']}")
with col2:
    new_fallback = pick_model("Fallback model", fallback,
                              f"fallback_{org['id']}", allow_none=True)

chosen = [m for m in (new_model, new_fallback) if m]
if any(provider_of(m) in FREE_TIER_PROVIDERS for m in chosen):
    st.warning(f"⚠️ {FREE_TIER_WARNING}")

st.caption(
    f"**Saved for {org['name']}:** {label_of(model)} → "
    f"{label_of(fallback) if fallback else 'no fallback'}")
if (new_model, new_fallback or None) != (model, fallback or None):
    st.warning("⚠️ Unsaved changes — click **Save models** to apply them.")

if st.session_state.pop("models_saved", False):
    st.success("Saved.")

save_col, test_col, _ = st.columns([1, 1, 3])
if save_col.button("💾 Save models", type="primary"):
    try:
        llm_settings_service.set_models(user, org["id"], new_model, new_fallback)
        st.session_state.models_saved = True
        st.rerun()
    except AuthError as e:
        st.error(str(e))

if test_col.button("🧪 Test models"):
    for m in chosen:
        try:
            answer = call_ai("Reply with the single word OK.", org_id=org["id"],
                             max_tokens=2000, only_model=m)
            st.success(f"{label_of(m)}: answered “{answer.strip()[:40]}”")
        except RuntimeError as e:
            st.error(f"{label_of(m)}: {e}")

st.divider()
st.subheader(f"🔑 AI keys for {org['name']}")
render_org_keys(user, org["id"], [provider_of(m) for m in chosen])
