"""Audit log: every change writes one ``events`` row (R-DOM-07)."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from plot.core.clock import Clock
from plot.db.models import Event


@dataclass(frozen=True)
class RequestContext:
    """Who asked for a change, carried into every event."""

    actor: str
    request_id: str


def record_event(
    session: Session,
    clock: Clock,
    request: RequestContext,
    action: str,
    *,
    domain_name: str | None = None,
    host_name: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
) -> Event:
    event = Event(
        ts=clock.now(),
        request_id=request.request_id,
        actor=request.actor,
        action=action,
        domain_name=domain_name,
        host_name=host_name,
        before=before,
        after=after,
    )
    session.add(event)
    return event


def domain_history(session: Session, domain_name: str) -> list[Event]:
    """Events about ``domain_name`` or its subordinate hosts, oldest first."""
    stmt = (
        select(Event)
        .where(
            or_(
                Event.domain_name == domain_name,
                Event.host_name == domain_name,
                Event.host_name.endswith("." + domain_name),
            )
        )
        .order_by(Event.id)
    )
    return list(session.scalars(stmt))
