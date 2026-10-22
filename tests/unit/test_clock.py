from datetime import UTC, datetime, timedelta, timezone

import pytest

from plot.core.clock import FakeClock, SystemClock, add_years

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def test_system_clock_is_utc_aware() -> None:
    assert SystemClock().now().utcoffset() == timedelta(0)


def test_fake_clock_advances_and_sets() -> None:
    clock = FakeClock(T0)
    clock.advance(20)
    assert clock.now() == T0 + timedelta(seconds=20)
    clock.advance(timedelta(days=1))
    assert clock.now() == T0 + timedelta(days=1, seconds=20)
    clock.set(T0)
    assert clock.now() == T0


def test_fake_clock_rejects_naive_non_utc_and_backwards() -> None:
    with pytest.raises(ValueError):
        FakeClock(datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        FakeClock(datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=7))))
    with pytest.raises(ValueError):
        FakeClock(T0).advance(-1)


def test_add_years_is_calendar_based() -> None:
    assert add_years(T0, 1) == datetime(2027, 3, 1, 12, 0, tzinfo=UTC)
    leap = datetime(2028, 2, 29, tzinfo=UTC)
    assert add_years(leap, 1) == datetime(2029, 2, 28, tzinfo=UTC)
    assert add_years(leap, 4) == datetime(2032, 2, 29, tzinfo=UTC)
