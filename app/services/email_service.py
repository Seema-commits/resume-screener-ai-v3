"""
Sends the app's emails (only "reset your password" for now) over SMTP.
Set up for Gmail with an App Password; any SMTP service works.

Secrets (via app/config.get_secret, never in code):
    SMTP_USER       the sending account, e.g. you@gmail.com
    SMTP_PASSWORD   its Gmail App Password (not your normal password)
    SMTP_HOST       default smtp.gmail.com
    SMTP_PORT       default 587 (STARTTLS); 465 uses SSL
    MAIL_FROM       default SMTP_USER
    APP_URL         this front end's address, used in links

Emails are plain text only, and the address and link are never logged.
"""

import smtplib
import ssl
import threading
from email.message import EmailMessage

from app.config import get_secret
from app.services.logging_service import log_event

SEND_TIMEOUT_SECONDS = 20


def app_url():
    """The configured address of this front end - never taken from the
    request, so a forged Host header can't redirect reset links."""

    url = (get_secret("APP_URL") or "").strip().rstrip("/")
    return url if url.startswith(("https://", "http://")) else None


def is_configured():
    return bool(get_secret("SMTP_USER") and get_secret("SMTP_PASSWORD") and app_url())


def _send(to, subject, body):
    user, password = get_secret("SMTP_USER"), get_secret("SMTP_PASSWORD")
    host = get_secret("SMTP_HOST") or "smtp.gmail.com"
    port = int(get_secret("SMTP_PORT") or 587)

    message = EmailMessage()      # refuses line breaks in headers
    message["From"] = get_secret("MAIL_FROM") or user
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    if port == 465:
        server = smtplib.SMTP_SSL(host, port, timeout=SEND_TIMEOUT_SECONDS, context=context)
    else:
        server = smtplib.SMTP(host, port, timeout=SEND_TIMEOUT_SECONDS)
    with server:
        if port != 465:
            server.starttls(context=context)
        server.login(user, password)
        server.send_message(message)


def _send_logged(to, subject, body):
    try:
        _send(to, subject, body)
    except Exception as e:
        # The error type only - no address, link or SMTP reply text
        log_event(session_id="auth", agent_name="email", event_type="email_error",
                  data={"error": type(e).__name__})


def send_password_reset(to, name, link, minutes):
    """Sends in the background, so a request for a real account takes
    as long as one for an unknown email (no account discovery)."""

    body = (
        f"Hi {name},\n\n"
        f"Someone asked to reset your TalentLens AI password. To choose a "
        f"new one, open this link within {minutes} minutes:\n\n"
        f"{link}\n\n"
        f"The link works once. If you didn't ask for this, ignore this "
        f"email - your password stays the same.\n"
    )
    threading.Thread(
        target=_send_logged, args=(to, "Reset your TalentLens AI password", body),
        daemon=True,
    ).start()


def send_interview_email(candidate_email, candidate_name):
    """Interview invitation (not wired into the app yet). Uses the same
    SMTP secrets instead of credentials in code."""

    _send(candidate_email, "Interview Invitation", (
        f"Dear {candidate_name},\n\n"
        f"Congratulations!\n\n"
        f"You have been shortlisted for the next round.\n\n"
        f"Our team will contact you shortly with interview details.\n\n"
        f"Regards,\nTalentLens AI\n"
    ))
