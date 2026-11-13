import sys
import os

# Make sure the project root (the folder containing "app/") is on
# sys.path, regardless of how this script gets launched. Locally,
# "python -m streamlit run ..." happens to add the current folder
# automatically, which is why this works without it on your own
# machine - but Streamlit Cloud launches scripts differently and
# never adds it, so "from app.X import Y" fails there without
# this explicit fix. Pages run through st.navigation below, so
# they get it too.
sys.path.insert(
    0,
    os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

import streamlit as st

from app.auth.permissions import has_permission
from app.database.init_db import init_db
from app.ui.auth_ui import (
    change_password_form,
    load_current_user,
    login_form,
    user_box,
)

st.set_page_config(
    page_title="TalentLens AI",
    page_icon="🎯",
    layout="wide"
)

# Entry point for every page: database -> login -> forced password
# change -> a menu with only the pages this user's role allows.
# Each page also calls require() itself, so hiding a page here is
# never the only check.

if not st.session_state.get("db_ready"):
    st.session_state.db_ready = init_db()

if not st.session_state.db_ready:
    st.error(
        "The database isn't reachable. Check DATABASE_URL in the "
        "app's secrets, then reload."
    )
    st.stop()

user = load_current_user()

if user is None:
    login_form()
    st.stop()

if user.must_change_password:
    change_password_form(user)
    st.stop()

# (page file, title, icon, action required to see it)
PAGES = [
    ("pages/screening.py", "Screen Resumes", "🎯", "run_scan"),
    ("pages/scan_history.py", "Scan History", "🗂️", "view_own_scans"),
    ("pages/users.py", "Users", "👥", "manage_users"),
    ("pages/settings.py", "Settings", "🔑", "view_settings"),
    ("pages/logs.py", "Logs", "🪵", "view_logs"),
]

user_box(user)

st.navigation([
    st.Page(path, title=title, icon=icon)
    for path, title, icon, action in PAGES
    if has_permission(user, action)
]).run()
