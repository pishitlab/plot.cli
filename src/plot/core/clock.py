"""Time source. Services read time only through ``Clock`` (SPEC §4.4)."""

from datetime import UTC, datetime, timedelta
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, timezone-aware UTC."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FakeClock:
    """Manually driven clock for tests and simulations."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = _require_utc(start or datetime(2026, 1, 1, tzinfo=UTC))

    def now(self) -> datetime:
        return self._now

    def set(self, when: datetime) -> None:
        self._now = _require_utc(when)

    def advance(self, delta: timedelta | float) -> None:
        if not isinstance(delta, timedelta):
            delta = timedelta(seconds=delta)
        if delta < timedelta(0):
            raise ValueError("clock cannot go backwards")
        self._now += delta


def add_years(when: datetime, years: int) -> datetime:
    """Calendar year arithmetic; 29 February maps to 28 February in non-leap years."""
    try:
        return when.replace(year=when.year + years)
    except ValueError:
        return when.replace(year=when.year + years, day=28)


def _require_utc(when: datetime) -> datetime:
    if when.utcoffset() != timedelta(0):
        raise ValueError("clock times must be timezone-aware UTC")
    return when.astimezone(UTC)
