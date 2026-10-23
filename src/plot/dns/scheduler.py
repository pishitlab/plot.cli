"""Delayed publishing: pending_changes -> published_state (R-PUB-05, 06, 09)."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from plot.core.settings import RuntimeSettings
from plot.db.models import Domain, PendingChange, PublishedState
from plot.dns.projector import Snapshot

# Applies one domain's change to the registry: (domain_name, published, wanted) -> None.
Applier = Callable[[str, Snapshot, Snapshot], None]

BACKOFF_CAP = 30.0


def propagation_delay(session: Session, domain_name: str, settings: RuntimeSettings) -> int:
    """R-PUB-05: the domain's override, else the global setting (also for deleted domains)."""
    override = session.scalars(
        select(Domain.delay_override).where(Domain.name == domain_name)
    ).one_or_none()
    return settings.propagation_delay if override is None else override


def schedule_change(
    session: Session, domain_name: str, snapshot: Snapshot, now: datetime, delay: int
) -> PendingChange:
    change = PendingChange(
        domain_name=domain_name,
        snapshot=snapshot,
        scheduled_at=now,
        apply_at=now + timedelta(seconds=delay),
    )
    session.add(change)
    session.flush()
    return change


def due_changes(session: Session, now: datetime) -> list[PendingChange]:
    """R-PUB-06: unapplied changes whose time has come, in ``(apply_at, id)`` order."""
    stmt = (
        select(PendingChange)
        .where(PendingChange.applied_at.is_(None), PendingChange.apply_at <= now)
        .order_by(PendingChange.apply_at, PendingChange.id)
    )
    return list(session.scalars(stmt))


def has_pending(session: Session, domain_name: str) -> bool:
    stmt = select(PendingChange.id).where(
        PendingChange.domain_name == domain_name, PendingChange.applied_at.is_(None)
    )
    return session.scalars(stmt.limit(1)).first() is not None


def published_snapshot(session: Session, domain_name: str) -> Snapshot:
    state = session.get(PublishedState, domain_name)
    return state.snapshot if state is not None else None


def mark_applied(session: Session, change: PendingChange, now: datetime) -> None:
    """Record ``change`` as published; older unapplied changes of the domain are superseded."""
    change.applied_at = now
    session.execute(
        update(PendingChange)
        .where(
            PendingChange.domain_name == change.domain_name,
            PendingChange.applied_at.is_(None),
            PendingChange.id < change.id,
        )
        .values(applied_at=now)
    )
    state = session.get(PublishedState, change.domain_name)
    if state is None:
        session.add(
            PublishedState(
                domain_name=change.domain_name, snapshot=change.snapshot, published_at=now
            )
        )
    else:
        state.snapshot = change.snapshot
        state.published_at = now
    session.flush()


class Backoff:
    """R-PUB-09: retry after 1, 2, 4, ... seconds, capped at 30."""

    def __init__(self) -> None:
        self.failures = 0

    def failed(self) -> float:
        self.failures += 1
        return min(2.0 ** (self.failures - 1), BACKOFF_CAP)

    def reset(self) -> None:
        self.failures = 0


@dataclass(frozen=True)
class RunResult:
    applied: list[str]  # domains whose registry data changed
    error: Exception | None = None  # the first failure of this pass
    failed: list[str] = field(default_factory=list)  # domains left pending for a retry


def apply_due(session: Session, now: datetime, applier: Applier) -> RunResult:
    """Apply every due change in ``(apply_at, id)`` order.

    A failure only holds back its own domain: that change stays pending for the next
    attempt (R-PUB-09) while other domains go ahead, so one change the registry rejects
    cannot stop all publishing. Only the newest due change per domain is applied, so the
    order within a domain is kept.
    """
    applied: list[str] = []
    failed: list[str] = []
    error: Exception | None = None
    due = due_changes(session, now)
    latest: dict[str, int] = {}
    for c in due:
        latest[c.domain_name] = max(latest.get(c.domain_name, 0), c.id)
    for change in due:
        if change.applied_at is not None or change.id != latest[change.domain_name]:
            continue  # a newer due change of the same domain wins; it supersedes this one
        current = published_snapshot(session, change.domain_name)
        if change.snapshot != current:
            try:
                applier(change.domain_name, current, change.snapshot)
            except Exception as err:
                failed.append(change.domain_name)
                error = error or err
                continue
            applied.append(change.domain_name)
        mark_applied(session, change, now)
    return RunResult(applied, error, failed)
