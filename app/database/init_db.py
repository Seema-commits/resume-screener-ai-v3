from app.database.db import Base, engine
from app.database.models import AgentLog


def init_db():
    """
    Creates DB tables if they don't exist, then creates the first
    Superadmin from secrets if there is none yet (see
    auth_service.bootstrap_superadmin).

    Returns True on success, False if the database is not configured
    or unreachable - the app can't run without it (logins, users and
    scan history live there).
    """

    if engine is None:
        print("[init_db] DATABASE_URL is not configured")
        return False

    try:
        Base.metadata.create_all(bind=engine)

        # create_all doesn't add indexes to a table that already
        # exists, so add any new agent_logs indexes here
        for index in AgentLog.__table__.indexes:
            index.create(bind=engine, checkfirst=True)

        from app.services.auth_service import bootstrap_superadmin
        from app.services.logging_service import purge_old_logs
        bootstrap_superadmin()
        purge_old_logs()            # at most once a day

        return True

    except Exception as e:
        print(f"[init_db] Database unavailable: {e}")
        return False
