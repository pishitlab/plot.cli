"""Small presentation helpers for templates (no business rules here)."""

from datetime import UTC, datetime


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def seconds_until(value: str, now: datetime | None = None) -> int:
    """Whole seconds from ``now`` until the ISO time ``value`` (0 when past)."""
    delta = parse_time(value) - (now or datetime.now(UTC))
    return max(0, int(delta.total_seconds() + 0.999))


def relative(value: str | None, now: datetime | None = None) -> str:
    if not value:
        return "never"
    seconds = int(((now or datetime.now(UTC)) - parse_time(value)).total_seconds())
    if seconds < 0:
        return f"in {-seconds}s"
    if seconds < 120:
        return f"{seconds}s ago"
    if seconds < 7200:
        return f"{seconds // 60}m ago"
    return value[:19].replace("T", " ") + " UTC"


def as_int(value: str) -> int | str:
    """Form numbers go to the API as integers; anything else is left for it to reject."""
    return int(value) if value.lstrip("-").isdigit() else value
