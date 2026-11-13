"""
Application logs, stored in the agent_logs table only (log files
were wiped on every restart, so the database is the one source).

Each event type belongs to a retention category; purge_old_logs()
deletes entries past their category's age at most once a day.
"""

import json
from datetime import datetime, timedelta

from sqlalchemy import false

from app.auth.permissions import has_permission
from app.context import get_current_user
from app.database.db import SessionLocal
from app.database.models import AgentLog

# ---------------------------------------------------
# Retention
# ---------------------------------------------------

AUDIT_EVENTS = {
    "login_success", "login_failed", "password_changed", "password_reset",
    "user_created", "user_activated", "user_deactivated", "org_created",
    "superadmin_created", "llm_models_changed", "org_key_set",
    "org_key_removed",
}
ERROR_EVENTS = {
    "error", "parse_error", "parse_batch_error", "batch_error",
    "ui_error", "scan_save_error",
}
# Large, for debugging only (masked prompts and full results)
DEBUG_EVENTS = {"llm_input", "parsed_profiles", "request", "response"}

RETENTION_DAYS = {"audit": 365, "error": 90, "debug": 7, "other": 90}
CATEGORY_EVENTS = {"audit": AUDIT_EVENTS, "error": ERROR_EVENTS,
                   "debug": DEBUG_EVENTS}

PURGE_EVERY = timedelta(hours=24)
_last_purge = None


def category_of(event_type):
    """audit / error / debug, or "other" (e.g. llm_call)."""

    return next((c for c, events in CATEGORY_EVENTS.items()
                 if event_type in events), "other")


def purge_old_logs(now=None, force=False):
    """Deletes entries older than their category's retention. Runs
    at most once a day per app process unless force=True. Returns
    the number of entries deleted."""

    global _last_purge
    now = now or datetime.utcnow()

    if not force and _last_purge and now - _last_purge < PURGE_EVERY:
        return 0
    _last_purge = now

    named = AUDIT_EVENTS | ERROR_EVENTS | DEBUG_EVENTS
    deleted = 0

    with SessionLocal() as db:
        for category, days in RETENTION_DAYS.items():
            events = AgentLog.event_type.in_(CATEGORY_EVENTS[category]) \
                if category in CATEGORY_EVENTS \
                else AgentLog.event_type.notin_(named)
            deleted += db.query(AgentLog).filter(
                events, AgentLog.created_at < now - timedelta(days=days)
            ).delete(synchronize_session=False)
        db.commit()

    return deleted


# ---------------------------------------------------
# Writing
# ---------------------------------------------------

def _current_ids():
    """(org_id, user_id) of the logged-in user, if any, so every
    log entry can be scoped by org like the other tables."""

    user = get_current_user()
    return (user.org_id, user.id) if user is not None else (None, None)


def log_event(session_id, agent_name, event_type, data):

    org_id, user_id = _current_ids()

    try:
        with SessionLocal() as db:
            db.add(AgentLog(
                org_id=org_id,
                user_id=user_id,
                session_id=session_id,
                agent_name=agent_name,
                event_type=event_type,
                data=json.loads(json.dumps(data, default=str)),
            ))
            db.commit()

    except Exception:
        # logging should never crash the app
        pass


# ---------------------------------------------------
# Reading (Logs page - Superadmin only)
# ---------------------------------------------------

def _filtered(db, viewer, errors_only=False, event_type=None,
              org_id=None, date_from=None, date_to=None):

    query = db.query(AgentLog)

    if not has_permission(viewer, "view_logs"):
        return query.filter(false())
    if errors_only:
        query = query.filter(AgentLog.event_type.in_(ERROR_EVENTS))
    if event_type:
        query = query.filter(AgentLog.event_type == event_type)
    if org_id:
        query = query.filter(AgentLog.org_id == org_id)
    if date_from:
        query = query.filter(AgentLog.created_at >= date_from)
    if date_to:
        query = query.filter(AgentLog.created_at < date_to + timedelta(days=1))

    return query


def count_logs(viewer, **filters):
    with SessionLocal() as db:
        return _filtered(db, viewer, **filters).count()


def list_logs(viewer, offset=0, limit=25, **filters):
    """Newest first. Filters: errors_only, event_type, org_id,
    date_from, date_to (dates)."""

    with SessionLocal() as db:
        return [{
            "created_at": log.created_at, "org_id": log.org_id,
            "user_id": log.user_id, "session_id": log.session_id,
            "agent_name": log.agent_name, "event_type": log.event_type,
            "data": log.data,
        } for log in _filtered(db, viewer, **filters)
            .order_by(AgentLog.created_at.desc(), AgentLog.id.desc())
            .offset(offset).limit(limit).all()]


def event_types(viewer):
    """Event types present, for the Logs page filter."""

    if not has_permission(viewer, "view_logs"):
        return []
    with SessionLocal() as db:
        return sorted(t for (t,) in db.query(AgentLog.event_type).distinct())
