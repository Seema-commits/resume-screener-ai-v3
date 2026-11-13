import streamlit as st

from app.auth.permissions import has_permission
from app.services import auth_service, scan_service
from app.services.results_display import render_full_results
from app.ui.auth_ui import require

user = require("view_own_scans")

sees_all = has_permission(user, "view_all_scans")
sees_team = sees_all or has_permission(user, "view_team_scans")

st.title("🗂️ Scan History")
st.caption(
    "All scans in all organizations." if sees_all else
    f"Every scan run by your team in {user.org_name}." if sees_team else
    "Scans you have run."
)

# ---------------------------------------------------
# FILTERS (they only narrow what the role may see -
# scan_service scopes every query by role)
# ---------------------------------------------------

org_id = user_id = None
cols = st.columns(4 if sees_all else 3 if sees_team else 2)
col = iter(cols)

if sees_all:
    orgs = auth_service.list_orgs(user)
    org = next(col).selectbox(
        "Organization", [None] + orgs,
        format_func=lambda o: "All" if o is None else o["name"])
    org_id = org and org["id"]

if sees_team:
    people = [u for u in auth_service.list_users(user)
              if not org_id or u["org_id"] == org_id]
    person = next(col).selectbox(
        "Run by", [None] + people,
        format_func=lambda u: "Everyone" if u is None else u["name"])
    user_id = person and person["id"]

dates = next(col).date_input("Date range", value=())
jd_query = next(col).text_input("JD contains")

date_from = dates[0] if len(dates) > 0 else None
date_to = dates[1] if len(dates) > 1 else date_from

scans = scan_service.list_scans(
    user, org_id=org_id, user_id=user_id, date_from=date_from,
    date_to=date_to, jd_query=jd_query.strip() or None)

if not scans:
    st.info("No scans found.")
    st.stop()

# ---------------------------------------------------
# SCAN LIST - select a row to open it
# ---------------------------------------------------

rows = [{
    "When (UTC)": s["created_at"].strftime("%Y-%m-%d %H:%M"),
    **({"Organization": s["org"]} if sees_all else {}),
    **({"Run by": s["run_by"]} if sees_team else {}),
    "Job description": " ".join(s["jd_text"].split())[:90],
    "Resumes": s["resume_count"],
    "Shortlisted": s["shortlisted_count"],
} for s in scans]

picked = st.dataframe(
    rows, hide_index=True, use_container_width=True,
    on_select="rerun", selection_mode="single-row")

selected = picked.selection.rows
if not selected:
    st.caption("Select a scan to see its full results.")
    st.stop()

scan = scan_service.load_scan(user, scans[selected[0]]["id"])
if scan is None:
    st.error("You don't have access to this scan.")
    st.stop()

st.divider()
with st.expander("📋 Job description"):
    st.text(scan["jd_text"])

render_full_results(scan, show_downloads=True)
