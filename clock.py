"""UTC time helpers. Every function that needs 'now' accepts it as an argument
so tests can use a fixed clock instead of waiting."""

from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc)


def to_iso(moment):
    """Aware datetime -> ISO-8601 UTC string (always ends in +00:00)."""
    if moment.tzinfo is None:
        raise ValueError("Naive datetime rejected: timestamps must be timezone-aware.")
    return moment.astimezone(timezone.utc).isoformat()


def parse_iso(text):
    """ISO-8601 string with an explicit offset -> aware UTC datetime."""
    try:
        moment = datetime.fromisoformat(str(text).strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"'{text}' is not a valid ISO-8601 timestamp.")
    if moment.tzinfo is None:
        raise ValueError(f"'{text}' has no timezone; use e.g. 2026-10-14T10:00:00+00:00.")
    return moment.astimezone(timezone.utc)
