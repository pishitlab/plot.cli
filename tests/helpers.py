"""Builders for unit tests that need rows without going through every service."""

from datetime import timedelta

from sqlalchemy.orm import Session

from plot.core.clock import Clock
from plot.db.models import Domain, DomainNs, Event, Host


def add_domain(session: Session, clock: Clock, name: str, owner: str = "alice") -> Domain:
    label, _, suffix = name.partition(".")
    now = clock.now()
    domain = Domain(
        name=name,
        suffix=suffix,
        label=label,
        owner=owner,
        auth_code="test",
        created_at=now,
        expires_at=now + timedelta(days=365),
        updated_at=now,
    )
    session.add(domain)
    session.flush()
    return domain


def use_as_ns(session: Session, domain: Domain, *hosts: Host) -> None:
    for position, host in enumerate(hosts):
        session.add(DomainNs(domain_id=domain.id, host_id=host.id, position=position))
    session.flush()


def actions(session: Session) -> list[str]:
    return [e.action for e in session.query(Event).order_by(Event.id)]
