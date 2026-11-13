"""Log retention and the Logs page queries."""

from datetime import date, datetime, timedelta

from conftest import make_world
from app.database.db import SessionLocal
from app.database.models import AgentLog
from app.services import logging_service
from app.services.logging_service import list_logs, count_logs, purge_old_logs


def add_log(event_type, days_old, org_id=None):
    with SessionLocal() as db:
        db.add(AgentLog(event_type=event_type, agent_name="t", session_id="t",
                        org_id=org_id, data={},
                        created_at=datetime.utcnow() - timedelta(days=days_old)))
        db.commit()


def remaining():
    with SessionLocal() as db:
        return sorted((log.event_type, round((datetime.utcnow() - log.created_at).days))
                      for log in db.query(AgentLog).filter_by(agent_name="t"))


def test_each_category_is_kept_for_its_own_period():
    for event_type, kept, gone in [("login_failed", 300, 400),   # audit 365
                                   ("ui_error", 80, 100),        # error 90
                                   ("llm_call", 80, 100),        # other 90
                                   ("llm_input", 5, 10)]:        # debug 7
        add_log(event_type, kept)
        add_log(event_type, gone)

    deleted = purge_old_logs(force=True)

    assert deleted == 4
    assert remaining() == [("llm_call", 80), ("llm_input", 5),
                           ("login_failed", 300), ("ui_error", 80)]


def test_purge_runs_at_most_once_a_day():
    purge_old_logs(force=True)
    add_log("llm_input", 30)
    assert purge_old_logs() == 0                 # within 24h: skipped
    later = datetime.utcnow() + timedelta(hours=25)
    assert purge_old_logs(now=later) == 1


def test_logs_are_superadmin_only_filtered_and_paged():
    admin, manager, exec_a1, exec_a2, exec_b, org = make_world()
    for i in range(30):
        add_log("ui_error" if i % 3 == 0 else "llm_call", 0, org["Org A"])

    assert count_logs(manager) == 0 and list_logs(manager) == []   # not allowed

    errors = count_logs(admin, errors_only=True, org_id=org["Org A"])
    assert errors == 10
    page1 = list_logs(admin, offset=0, limit=25, org_id=org["Org A"])
    page2 = list_logs(admin, offset=25, limit=25, org_id=org["Org A"])
    assert len(page1) == 25 and len(page2) == 5
    assert count_logs(admin, date_from=date.today() + timedelta(days=1)) == 0
    assert "llm_call" in logging_service.event_types(admin)
