"""
Sets a new password for any user from the command line - the way back
in when the Superadmin has forgotten theirs (no email needed).

    python -m app.scripts.reset_password

Needs DATABASE_URL in the environment or a .env file. The password is
typed in hidden and only its bcrypt hash is stored. It also unlocks
the account.
"""

from getpass import getpass

from app.database.init_db import init_db
from app.services.auth_service import AuthError, set_password_from_cli


def main():
    if not init_db():
        raise SystemExit("Database not reachable - check DATABASE_URL.")

    email = input("Email of the account: ")
    password = getpass("New password (at least 10 characters): ")

    if getpass("Confirm new password: ") != password:
        raise SystemExit("Passwords don't match.")

    try:
        set_password_from_cli(email, password)
    except AuthError as e:
        raise SystemExit(str(e))
    print("Password updated - sign in with the new password.")


if __name__ == "__main__":
    main()
