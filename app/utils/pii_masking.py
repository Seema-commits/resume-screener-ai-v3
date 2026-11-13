"""
Masks a candidate's name, email, phone number and profile links in
resume text before it is sent to the LLM, and puts the real name back
into the results afterwards, so the UI still shows it.

Same philosophy as date_utils.py: plain Python, no LLM. Best effort -
a name is only masked where it appears as written on the resume's
first line (or in the file name, if that line isn't a name).
"""

import re

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\(?\d[\d\s().-]{7,}\d")
PROFILE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:linkedin|github)\.com/\S+",
    re.IGNORECASE
)
NAME_LINE_RE = re.compile(r"[A-Za-z][A-Za-z.'-]*(?: [A-Za-z][A-Za-z.'-]*){1,3}")
NOT_A_NAME = ("resume", "curriculum", "vitae", "profile")


def _mask_phone(match):
    digits = sum(ch.isdigit() for ch in match.group())
    # 9+ digits is a phone number, not a date range like "2016-2019"
    return "[PHONE]" if 9 <= digits <= 15 else match.group()


def _candidate_name(header, body):
    """The resume's own name line if it looks like one, else the
    name parser_service derived from the file name."""

    first_line = next(
        (line.strip() for line in body.splitlines() if line.strip()), ""
    )

    if (
        NAME_LINE_RE.fullmatch(first_line)
        and not any(w in first_line.lower() for w in NOT_A_NAME)
    ):
        return first_line

    return header.split(":", 1)[-1].strip(" -")


def mask_resume(chunk, token):
    """
    chunk: one "--- Candidate N: name ---" block from parser_service.
    token: the ID that replaces the name (e.g. "CANDIDATE_1A2B3C").
    Returns (masked chunk, contact), where contact is the real
    {"name", "email", "phone"} found - kept in the app for the
    recruiter, never sent to the LLM.
    """

    header, _, body = chunk.partition("\n")

    email = EMAIL_RE.search(body)
    phones = (
        m.group() for m in PHONE_RE.finditer(body)
        if _mask_phone(m) == "[PHONE]"
    )
    contact = {
        "name": _candidate_name(header, body),
        "email": email.group() if email else None,
        "phone": next(phones, None),
    }
    name = contact["name"]

    body = PROFILE_URL_RE.sub("[PROFILE_URL]", body)
    body = EMAIL_RE.sub("[EMAIL]", body)
    body = PHONE_RE.sub(_mask_phone, body)

    # Full name first, then each part ("Aisha", "Rahman") on its own
    for part in [name] + sorted(name.split(), key=len, reverse=True):
        if len(part) >= 3:
            body = re.sub(
                rf"\b{re.escape(part)}\b", token, body,
                flags=re.IGNORECASE
            )

    masked_header = header.split(":", 1)[0] + f": {token} ---"

    return f"{masked_header}\n{body}", contact


def unmask(value, names):
    """Replaces every token in `names` ({token: real name}) inside a
    string, or recursively inside lists and dicts of them."""

    if isinstance(value, str):
        for token, name in names.items():
            value = value.replace(token, name)
        return value

    if isinstance(value, list):
        return [unmask(v, names) for v in value]

    if isinstance(value, dict):
        return {k: unmask(v, names) for k, v in value.items()}

    return value
