"""
Creates a Superadmin account from the command line.

    python -m app.scripts.create_superadmin

Needs DATABASE_URL in the environment or a .env file. The password
is typed in hidden and only its bcrypt hash is stored. (On Streamlit
Cloud you can use the BOOTSTRAP_SUPERADMIN_* secrets instead - see
auth_service.bootstrap_superadmin.)
"""

from getpass import getpass

from app.database.init_db import init_db
from app.services.auth_service import AuthError, create_superadmin


def main():
    if not init_db():
        raise SystemExit("Database not reachable - check DATABASE_URL.")

    name = input("Name: ")
    email = input("Email (used to sign in): ")
    password = getpass("Password (at least 10 characters): ")

    if getpass("Confirm password: ") != password:
        raise SystemExit("Passwords don't match.")

    try:
        create_superadmin(name, email, password, must_change_password=False)
    except AuthError as e:
        raise SystemExit(str(e))

    print(f"Superadmin {email.strip().lower()} created.")


if __name__ == "__main__":
    main()
