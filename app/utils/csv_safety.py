"""CSV injection guard (OWASP): text a spreadsheet would run as a formula -
starting with = + - @ or a tab/carriage return - gets a leading ' so it
shows as plain text. The React app does the same in frontend/src/lib/csv.ts."""

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text.startswith(FORMULA_START) else text
