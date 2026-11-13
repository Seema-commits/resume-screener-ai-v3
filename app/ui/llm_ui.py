"""
Shared UI for an org's AI provider keys - used on the Settings page
(Superadmin, any org) and the Users page (HR Manager, own org). Keys
are write-only: once saved, only their last 4 characters are shown.
"""

import streamlit as st

from app.llm_config import PROVIDER_KEY_SECRETS
from app.services import llm_settings_service
from app.services.auth_service import AuthError


def render_org_keys(actor, org_id, providers):
    """A row per provider the org's models need: status, and a form
    to set/replace or remove the key."""

    status = llm_settings_service.key_status(actor, org_id)
    providers = list(dict.fromkeys(providers))

    if llm_settings_service.is_admin_org(org_id):
        st.caption("This organization uses the keys in the app's Secrets.")
        for p in providers:
            secret = PROVIDER_KEY_SECRETS.get(p, f"{p.upper()}_API_KEY")
            st.write(f"{'✅' if p in status else '❌'} **{p}** — `{secret}`")
        return

    for provider in providers:

        current = status.get(provider)
        st.write(
            f"{'✅' if current else '❌'} **{provider}** — "
            + (f"key set, ends in {current[1:]}" if current else "no key yet"))

        with st.form(f"key_{org_id}_{provider}", clear_on_submit=True):
            key = st.text_input(
                f"{'Replace' if current else 'Set'} {provider} key",
                type="password", placeholder="Paste the API key")
            save = st.form_submit_button("Save key")

        try:
            if save:
                llm_settings_service.set_key(actor, org_id, provider, key)
                st.rerun()
            if current and st.button(
                    f"Remove {provider} key", key=f"rm_{org_id}_{provider}"):
                llm_settings_service.remove_key(actor, org_id, provider)
                st.rerun()
        except AuthError as e:
            st.error(str(e))
