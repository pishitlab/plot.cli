"""Expiry, grace period and purge: R-DOM-06 (SPEC §6.2)."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, Delete, delete, select

from plot.db.models import Domain, Event, PendingChange, PublishedState
from plot.services.context import ServiceContext
from plot.services.domains import DomainService, DomainView, domain_view, remove_domain

# Housekeeping: how long finished bookkeeping rows are kept.
APPLIED_CHANGE_RETENTION = timedelta(days=1)
EVENT_RETENTION = timedelta(days=90)


@dataclass(frozen=True)
class LifecycleResult:
    expired: list[str]
    purged: list[str]


class LifecycleService:
    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx
        self.session = ctx.session

    def run(self, since: datetime | None = None) -> LifecycleResult:
        """Purge domains past their grace period and republish domains that expired.

        ``since`` is the time of the previous run; domains that expired in ``[since, now)``
        lose their delegation (R-PUB-02). ``None`` republishes every expired domain.
        """
        now = self.ctx.clock.now()
        grace_end = now - timedelta(days=self.ctx.settings.expiry_grace_days)
        purged = []
        for domain in self.session.scalars(
            select(Domain).where(Domain.expires_at < grace_end).order_by(Domain.name)
        ):
            purged.append(domain.name)
            remove_domain(self.ctx, domain, action="domain.purge", force=True)

        expired_stmt = select(Domain.name).where(Domain.expires_at < now).order_by(Domain.name)
        if since is not None:
            expired_stmt = expired_stmt.where(Domain.expires_at >= since)
        expired = list(self.session.scalars(expired_stmt))
        if expired:
            self.ctx.publisher.domains_changed(self.session, expired)
        return LifecycleResult(expired=expired, purged=purged)

    def prune(self) -> int:
        """Delete bookkeeping that no longer matters, so the database stays small:
        applied changes after a day, events after 90 days, and the "nothing in DNS" state of
        domains that no longer exist and have nothing pending (reconcile treats a missing
        row the same)."""
        now = self.ctx.clock.now()
        removed = self._delete(
            delete(PendingChange).where(
                PendingChange.applied_at.is_not(None),
                PendingChange.applied_at < now - APPLIED_CHANGE_RETENTION,
            )
        )
        removed += self._delete(delete(Event).where(Event.ts < now - EVENT_RETENTION))
        keep = set(
            self.session.scalars(
                select(PendingChange.domain_name).where(PendingChange.applied_at.is_(None))
            )
        ) | set(self.session.scalars(select(Domain.name)))
        for state in self.session.scalars(select(PublishedState)).all():
            if state.snapshot is None and state.domain_name not in keep:
                self.session.delete(state)
                removed += 1
        self.session.flush()
        return removed

    def _delete(self, statement: Delete) -> int:
        result = cast(CursorResult[Any], self.session.execute(statement))
        return result.rowcount

    def expire_now(self, raw_name: str) -> DomainView:
        """Admin test hook: move ``expires_at`` into the past so the domain is expired."""
        domain = DomainService(self.ctx).load(raw_name)
        before = domain_view(self.ctx, domain)
        now = self.ctx.clock.now()
        domain.expires_at = now - timedelta(seconds=1)
        domain.updated_at = now
        self.session.flush()
        after = domain_view(self.ctx, domain)
        self.ctx.record(
            "domain.expire_now",
            domain_name=domain.name,
            before=before.to_event(),
            after=after.to_event(),
        )
        self.ctx.publisher.domains_changed(self.session, {domain.name})
        return after
