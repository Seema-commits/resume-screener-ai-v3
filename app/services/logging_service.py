import json
import os
from datetime import datetime

from app.database.db import SessionLocal
from app.database.models import AgentLog


LOG_FOLDER = "logs"


def _current_ids():
    """(org_id, user_id) of the logged-in user, if any, so every
    log entry can be scoped by org like the other tables."""

    try:
        import streamlit as st
        user = st.session_state.get("current_user")
        if user is not None:
            return user.org_id, user.id
    except Exception:
        pass

    return None, None


def ensure_log_folder():

    if not os.path.exists(LOG_FOLDER):

        os.makedirs(LOG_FOLDER)


def log_event(
    session_id,
    agent_name,
    event_type,
    data
):

    timestamp = datetime.utcnow().isoformat()
    org_id, user_id = _current_ids()

    log_entry = {
        "timestamp": timestamp,
        "org_id": org_id,
        "user_id": user_id,
        "session_id": session_id,
        "agent_name": agent_name,
        "event_type": event_type,
        "data": data
    }

    # -----------------------------------
    # Local file (kept for backward
    # compatibility with anything else
    # reading these log files directly)
    # -----------------------------------

    try:

        ensure_log_folder()

        log_file = os.path.join(
            LOG_FOLDER,
            f"{session_id}.log"
        )

        with open(log_file, "a") as f:

            f.write(json.dumps(log_entry, default=str))
            f.write("\n")

    except Exception:
        # logging should never crash the app
        pass

    # -----------------------------------
    # Database (agent_logs table) - this
    # is what the Logs page and the
    # dashboard's Audit Logs section read
    # from, so errors are actually visible
    # in the UI, not just on disk.
    # -----------------------------------

    try:

        db = SessionLocal()

        entry = AgentLog(
            org_id=org_id,
            user_id=user_id,
            session_id=session_id,
            agent_name=agent_name,
            event_type=event_type,
            data=json.loads(
                json.dumps(data, default=str)
            )
        )

        db.add(entry)
        db.commit()
        db.close()

    except Exception:
        # logging should never crash the app -
        # if the DB write fails, the file write
        # above still happened
        pass