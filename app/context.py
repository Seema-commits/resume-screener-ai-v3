"""
Who is making the current request - one helper for both front ends.

FastAPI sets it per request (backend/deps.py) with set_current_user;
under Streamlit it falls back to st.session_state.current_user (set
by app/ui/auth_ui.py). Services such as logging and the LLM client
read it with get_current_user().
"""

from contextvars import ContextVar

_current_user = ContextVar("current_user", default=None)


def set_current_user(user):
    """Returns a token for resetting it (ContextVar.reset)."""
    return _current_user.set(user)


def get_current_user():
    user = _current_user.get()
    if user is not None:
        return user

    try:
        from streamlit import runtime
        if not runtime.exists():          # not inside the Streamlit app
            return None
        import streamlit as st
        return st.session_state.get("current_user")
    except Exception:
        return None
