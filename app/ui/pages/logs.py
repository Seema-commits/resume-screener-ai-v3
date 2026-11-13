import streamlit as st

from app.services import auth_service, logging_service
from app.services.logging_service import RETENTION_DAYS, category_of
from app.ui.auth_ui import require
from app.ui.pagination import PAGE_SIZE, paginate

user = require("view_logs")

st.title("🪵 Application Logs")
st.caption(
    f"Kept automatically for: security/audit events "
    f"{RETENTION_DAYS['audit']} days · errors {RETENTION_DAYS['error']} "
    f"days · AI calls and other events {RETENTION_DAYS['other']} days · "
    f"debug detail (masked prompts, full results) "
    f"{RETENTION_DAYS['debug']} days. Older entries are deleted daily.")

# ---------------------------------------------------
# FILTERS
# ---------------------------------------------------

errors_only = st.toggle("Errors only", value=False)

col1, col2, col3 = st.columns(3)
event_type = col1.selectbox(
    "Event type", [None] + logging_service.event_types(user),
    format_func=lambda e: "All" if e is None else e)
org = col2.selectbox(
    "Organization", [None] + auth_service.list_orgs(user),
    format_func=lambda o: "All" if o is None else o["name"])
dates = col3.date_input("Date range", value=())

filters = {
    "errors_only": errors_only,
    "event_type": event_type,
    "org_id": org and org["id"],
    "date_from": dates[0] if len(dates) > 0 else None,
    "date_to": dates[1] if len(dates) > 1 else (dates[0] if dates else None),
}

# ---------------------------------------------------
# ENTRIES (newest first, 25 per page)
# ---------------------------------------------------

total = logging_service.count_logs(user, **filters)
offset = paginate(total, "logs", filters)

ICONS = {"error": "🔴", "audit": "🛡️", "debug": "🔍", "other": "🔵"}

for log in logging_service.list_logs(user, offset=offset, limit=PAGE_SIZE,
                                     **filters):
    category = category_of(log["event_type"])
    with st.expander(
        f"{ICONS[category]} {log['event_type']} — {log['agent_name']} — "
        f"{log['created_at']:%Y-%m-%d %H:%M:%S} UTC"
    ):
        st.caption(
            f"Org {log['org_id'] or '–'} · user {log['user_id'] or '–'} · "
            f"session {log['session_id']} · kept {RETENTION_DAYS[category]} days")
        st.json(log["data"] or {})
