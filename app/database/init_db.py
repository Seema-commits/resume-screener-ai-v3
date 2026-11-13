from app.database.db import Base, engine
import app.database.models  # noqa: F401 - registers the tables on Base


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

        from app.services.auth_service import bootstrap_superadmin
        bootstrap_superadmin()

        return True

    except Exception as e:
        print(f"[init_db] Database unavailable: {e}")
        return False
