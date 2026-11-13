import json
import glob
import os

import streamlit as st

from app.ui.auth_ui import require

require("view_logs")

st.title("🪵 Application Logs")

st.caption(
    "Reads directly from local log files - works without any "
    "database setup. Parsing/scoring errors and unexpected "
    "failures are logged here automatically. If a screening run "
    "behaved unexpectedly, check here first."
)

LOG_FOLDER = "logs"

ERROR_EVENT_TYPES = (
    "error", "parse_error", "parse_batch_error",
    "batch_error", "ui_error"
)


def load_all_logs():
    """
    Reads every *.log file in the logs/ folder (one per session_id)
    and returns all entries, newest first. Each line in a log file
    is one JSON object, written by logging_service.log_event().
    """

    entries = []

    if not os.path.isdir(LOG_FOLDER):
        return entries

    log_files = glob.glob(os.path.join(LOG_FOLDER, "*.log"))

    for file_path in log_files:

        try:

            with open(file_path, "r") as f:

                for line in f:

                    line = line.strip()

                    if not line:
                        continue

                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        except Exception:
            continue

    entries.sort(
        key=lambda e: e.get("timestamp", ""),
        reverse=True
    )

    return entries


show_all = st.toggle("Show all events (not just errors)", value=False)

all_logs = load_all_logs()

if show_all:
    logs = all_logs
else:
    logs = [
        log for log in all_logs
        if log.get("event_type") in ERROR_EVENT_TYPES
    ]

if not logs:

    st.info(
        "No errors logged yet."
        if not show_all
        else "No log events found yet."
    )

else:

    for log in logs[:300]:

        event_type = log.get("event_type", "unknown")
        agent_name = log.get("agent_name", "unknown")
        timestamp = log.get("timestamp", "")
        session_id = log.get("session_id", "unknown")

        is_error = event_type in ERROR_EVENT_TYPES
        icon = "🔴" if is_error else "🔵"

        with st.expander(
            f"{icon} {event_type} — {agent_name} — {timestamp}"
        ):

            st.write(f"**Session:** {session_id}")
            st.json(log.get("data", {}))

st.divider()
st.caption(
    f"Showing up to 300 most recent "
    f"{'events' if show_all else 'errors'}, across all sessions, "
    f"reading directly from the logs/ folder."
)