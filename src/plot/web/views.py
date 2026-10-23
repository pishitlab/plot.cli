"""Small presentation helpers for templates (no business rules here)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


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


@dataclass(frozen=True)
class DnsPanel:
    published_at: str | None
    visible: list[str]
    in_db: list[str]
    pending_seconds: list[int]  # seconds until each pending change applies
    in_sync: bool


def dns_panel(domain: dict[str, Any], now: datetime | None = None) -> DnsPanel:
    """What DNS shows versus the registry database (D-007), for the domain page."""
    visible = domain["dns_visible"]
    pending = [seconds_until(p["apply_at"], now) for p in visible["pending"]]
    return DnsPanel(
        published_at=visible["published_at"],
        visible=visible["nameservers"],
        in_db=domain["nameservers"],
        pending_seconds=pending,
        in_sync=not pending,
    )


def override_body(delay: str, ttl: str) -> dict[str, Any]:
    """Blank leaves a value unchanged, ``none`` clears it (like ``plot override``)."""
    body: dict[str, Any] = {}
    for key, raw in (("propagation_delay", delay), ("ns_ttl", ttl)):
        if raw:
            body[key] = None if raw.lower() == "none" else as_int(raw)
    return body


def event_row(event: dict[str, Any]) -> dict[str, Any]:
    """An event with the fields that changed between ``before`` and ``after``."""
    before, after = event.get("before") or {}, event.get("after") or {}
    changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
    return {**event, "changes": [(k, before.get(k), after.get(k)) for k in changed]}
