"""
Streamlit side of login: the login and password-change forms, the
sidebar user box, and require(), which every page calls first.
Decisions themselves come from app/auth/permissions.py.
"""

import streamlit as st

from app.auth.permissions import ROLE_LABELS, has_permission
from app.services import auth_service
from app.services.auth_service import AuthError


def load_current_user():
    """The logged-in user (re-read from the DB on every run), or None.
    A user deactivated or locked mid-session is logged out here."""

    user_id = st.session_state.get("user_id")
    user = auth_service.load_user(user_id) if user_id else None

    if user_id and user is None:
        st.session_state.clear()

    st.session_state.current_user = user
    return user


def require(action):
    """Stops the page unless the current user may do `action`.
    Hiding a page from the menu is never the only check."""

    user = st.session_state.get("current_user")

    if not has_permission(user, action):
        st.error("You don't have access to this page.")
        st.stop()

    return user


def show_temp_password(email, password):
    """Shown once - it isn't stored anywhere it could be shown again."""

    st.success(
        f"Temporary password for **{email}** - share it securely. It "
        f"won't be shown again, and must be changed at first login."
    )
    st.code(password, language=None)


RESET_PARAM = "reset_token"
RESET_LINK_PATH = f"/?{RESET_PARAM}="
RESET_SENT = (
    "If that email belongs to an active account, we've sent a link to "
    "reset the password. It works once, for 30 minutes - check your spam "
    "folder too."
)


def login_form():
    # A reset link opens here. The token is moved out of the address
    # bar at once, so it isn't left in the browser history.
    token = st.query_params.get(RESET_PARAM)
    if token:
        st.session_state.reset_token = token
        del st.query_params[RESET_PARAM]

    if st.session_state.get("reset_token"):
        return reset_password_form()
    if st.session_state.get("show_forgot_password"):
        return forgot_password_form()

    st.title("🎯 TalentLens AI")
    st.subheader("Sign in")
    if st.session_state.pop("password_was_reset", False):
        st.success("Password changed - sign in with your new password.")

    with st.form("login"):
        email = st.text_input("Email")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary")

    if st.button("Forgot password?", type="tertiary"):
        st.session_state.show_forgot_password = True
        st.rerun()

    if submitted:
        try:
            user = auth_service.authenticate(email, password)
        except AuthError as e:
            st.error(str(e))
            return
        st.session_state.user_id = user.id
        st.rerun()


def forgot_password_form():
    st.title("🎯 TalentLens AI")
    st.subheader("Forgot password")

    with st.form("forgot_password"):
        email = st.text_input("Your account email")
        submitted = st.form_submit_button("Email me a reset link", type="primary")

    if submitted:
        try:
            auth_service.request_password_reset(email, RESET_LINK_PATH)
            st.success(RESET_SENT)       # same message for any email
        except AuthError as e:
            st.warning(str(e))

    if st.button("Back to sign in", type="tertiary"):
        st.session_state.pop("show_forgot_password", None)
        st.rerun()


def reset_password_form():
    st.title("🎯 TalentLens AI")
    st.subheader("Choose a new password")

    with st.form("reset_password"):
        new = st.text_input(
            f"New password (at least {auth_service.MIN_PASSWORD_LENGTH} "
            f"characters)", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Save password", type="primary")

    if submitted:
        if new != confirm:
            st.error("The new passwords don't match.")
            return
        try:
            auth_service.reset_password_with_token(
                st.session_state.reset_token, new)
        except AuthError as e:
            st.error(str(e))
            return
        st.session_state.pop("reset_token", None)
        st.session_state.pop("show_forgot_password", None)
        st.session_state.password_was_reset = True
        st.rerun()

    if st.button("Back to sign in", type="tertiary"):
        st.session_state.pop("reset_token", None)
        st.rerun()


def change_password_form(user):
    st.title("🎯 TalentLens AI")
    st.subheader("Set a new password")
    st.info("You're using a temporary password. Choose your own to continue.")

    with st.form("change_password"):
        current = st.text_input("Temporary password", type="password")
        new = st.text_input(
            f"New password (at least {auth_service.MIN_PASSWORD_LENGTH} "
            f"characters)", type="password")
        confirm = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Save password", type="primary")

    if submitted:
        if new != confirm:
            st.error("The new passwords don't match.")
            return
        try:
            auth_service.change_password(user.id, current, new)
        except AuthError as e:
            st.error(str(e))
            return
        st.rerun()


def user_box(user):
    with st.sidebar:
        st.markdown(f"**{user.name}**  \n{ROLE_LABELS[user.role]} · {user.org_name}")
        if st.button("Sign out"):
            st.session_state.clear()
            st.rerun()
        st.divider()
