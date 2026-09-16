"""Read-only SQL safety guardrail. Applied to every query before execution,
whether it came from a template match or (if ever added) an LLM fallback."""
import re

_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|PRAGMA|VACUUM|GRANT|REVOKE)\b",
    re.IGNORECASE,
)
_SELECT_START = re.compile(r"^\s*(WITH\b.*?\bSELECT\b|SELECT\b)", re.IGNORECASE | re.DOTALL)


def is_read_only(sql: str) -> bool:
    """True only for a single, standalone SELECT (optionally with a leading
    WITH/CTE clause) containing no DDL/DML keywords and no statement-stacking."""
    stripped = sql.strip().rstrip(";").strip()
    if not stripped:
        return False
    if not _SELECT_START.match(stripped):
        return False
    if _FORBIDDEN.search(stripped):
        return False
    if ";" in stripped:  # reject stacked statements
        return False
    return True
