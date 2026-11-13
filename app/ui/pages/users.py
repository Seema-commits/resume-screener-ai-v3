import streamlit as st

from app.auth.permissions import MANAGEABLE_ROLES, ROLE_LABELS, has_permission
from app.llm_config import label_of, provider_of
from app.services import auth_service, llm_settings_service
from app.services.auth_service import AuthError
from app.ui.auth_ui import require, show_temp_password
from app.ui.llm_ui import render_org_keys

user = require("manage_users")
manages_orgs = has_permission(user, "manage_orgs")

st.title("👥 Users")

# Every action below is re-checked in auth_service (can_manage), so
# the options offered here are a convenience, not the protection.

# ---------------------------------------------------
# ORGANIZATIONS (Superadmin only)
# ---------------------------------------------------

orgs = auth_service.list_orgs(user)

if manages_orgs:
    st.subheader("Organizations")
    st.dataframe(
        [{"Organization": o["name"],
          "Status": "Active" if o["is_active"] else "Inactive"}
         for o in orgs],
        hide_index=True, use_container_width=True)

    with st.form("create_org", clear_on_submit=True):
        org_name = st.text_input("New organization name")
        if st.form_submit_button("Create organization"):
            try:
                auth_service.create_org(user, org_name)
                st.success(f"Created {org_name}.")
                st.rerun()
            except AuthError as e:
                st.error(str(e))

    st.divider()

# ---------------------------------------------------
# ADD A USER
# ---------------------------------------------------

st.subheader("Add a user")

roles = sorted(MANAGEABLE_ROLES[user.role])
active_orgs = [o for o in orgs if o["is_active"]]

with st.form("create_user", clear_on_submit=True):
    name = st.text_input("Name")
    email = st.text_input("Email (used to sign in)")
    role = st.selectbox("Role", roles, format_func=ROLE_LABELS.get)
    if manages_orgs:
        org = st.selectbox("Organization", active_orgs,
                           format_func=lambda o: o["name"])
    else:
        org = {"id": user.org_id}
        st.caption(f"Organization: {user.org_name}")
    submitted = st.form_submit_button("Create user", type="primary")

if submitted:
    try:
        temp = auth_service.create_user(
            user, org and org["id"], name, email, role)
        show_temp_password(email.strip().lower(), temp)
    except AuthError as e:
        st.error(str(e))

st.divider()

# ---------------------------------------------------
# USER LIST + ACTIONS
# ---------------------------------------------------

st.subheader("All users" if manages_orgs else f"Team in {user.org_name}")

users = auth_service.list_users(user)

st.dataframe([{
    "Name": u["name"],
    "Email": u["email"],
    "Role": ROLE_LABELS[u["role"]],
    **({"Organization": u["org_name"]} if manages_orgs else {}),
    "Status": u["status"],
    "Created by": u["created_by"],
    "Last login (UTC)": (u["last_login_at"].strftime("%Y-%m-%d %H:%M")
                         if u["last_login_at"] else ""),
} for u in users], hide_index=True, use_container_width=True)

manageable = [u for u in users if u["manageable"]]

if manageable:
    target = st.selectbox(
        "Manage a user", manageable,
        format_func=lambda u: f"{u['name']} ({u['email']}) - {u['status']}")

    col1, col2 = st.columns(2)

    toggle = col1.button(
        "Deactivate" if target["is_active"] else "Reactivate")
    reset = col2.button(
        "Unlock & reset password" if target["status"] == "Locked"
        else "Reset password")

    try:
        if toggle:
            auth_service.set_active(
                user, target["id"], not target["is_active"])
            st.rerun()
        if reset:
            show_temp_password(
                target["email"],
                auth_service.reset_password(user, target["id"]))
    except AuthError as e:
        st.error(str(e))

# ---------------------------------------------------
# OWN ORG'S AI KEY (HR Manager - the Superadmin sets
# every org's keys on the Settings page)
# ---------------------------------------------------

if not manages_orgs and has_permission(user, "manage_org_keys"):
    st.divider()
    st.subheader(f"🔑 AI key for {user.org_name}")
    models = [m for m in llm_settings_service.models_for_org(user.org_id) if m]
    st.caption(
        "Your team's scans use " + " → ".join(label_of(m) for m in models)
        + ". Keys are stored encrypted and never shown again after saving.")
    render_org_keys(user, user.org_id, [provider_of(m) for m in models])
