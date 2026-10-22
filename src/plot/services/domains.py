"""Domains: check, register, renew, delete, status, overrides (R-DOM-01..05, SPEC §6.2)."""

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final

from sqlalchemy import select

from plot.core.clock import add_years
from plot.core.errors import (
    BadRequestError,
    DomainExists,
    DomainNotFound,
    DomainPurged,
    HostInUse,
    InvalidPeriod,
    InvalidStatus,
    RenewLimit,
    ValidationFailed,
)
from plot.core.names import normalize_name
from plot.core.settings import MAX_TTL
from plot.db.models import Domain, DomainStatus, Host
from plot.services.context import ServiceContext
from plot.services.hosts import (
    delete_unused_external_hosts,
    glue_owners,
    host_used_by,
    host_view,
)

MAX_YEARS = 10
SETTABLE_STATUSES = frozenset({"clientHold", "serverHold", "pendingDelete"})
DEFAULT_LIST_LIMIT = 50
MAX_LIST_LIMIT = 200


class _Unset:
    pass


UNSET: Final = _Unset()


@dataclass(frozen=True)
class Overrides:
    propagation_delay: int | None
    ns_ttl: int | None


@dataclass(frozen=True)
class DomainView:
    name: str
    owner: str
    status: list[str]
    expired: bool
    created_at: datetime
    expires_at: datetime
    nameservers: list[str]
    overrides: Overrides

    def to_event(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "owner": self.owner,
            "status": self.status,
            "expires_at": self.expires_at.isoformat(),
            "nameservers": self.nameservers,
            "overrides": {
                "propagation_delay": self.overrides.propagation_delay,
                "ns_ttl": self.overrides.ns_ttl,
            },
        }


@dataclass(frozen=True)
class CheckResult:
    name: str
    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class DomainPage:
    items: list[DomainView]
    next_cursor: str | None


def is_expired(domain: Domain, now: datetime) -> bool:
    """R-DOM-06: expired is derived, ``now > expires_at``."""
    return now > domain.expires_at


def is_past_grace(domain: Domain, now: datetime, grace_days: int) -> bool:
    return now > domain.expires_at + timedelta(days=grace_days)


def find_domain(ctx: ServiceContext, name: str) -> Domain | None:
    return ctx.session.scalars(select(Domain).where(Domain.name == name)).one_or_none()


def domain_view(ctx: ServiceContext, domain: Domain) -> DomainView:
    return DomainView(
        name=domain.name,
        owner=domain.owner,
        status=sorted(s.status for s in domain.statuses),
        expired=is_expired(domain, ctx.clock.now()),
        created_at=domain.created_at,
        expires_at=domain.expires_at,
        nameservers=[link.host.name for link in domain.nameservers],
        overrides=Overrides(domain.delay_override, domain.ns_ttl_override),
    )


def remove_domain(ctx: ServiceContext, domain: Domain, *, action: str, force: bool) -> None:
    """Delete ``domain`` with its subordinate hosts and free the name.

    Without ``force`` a subordinate host still used by another domain blocks the delete
    (R-DOM-04). With ``force`` (purge) such hosts are dropped from those domains' NS sets.
    """
    session = ctx.session
    before = domain_view(ctx, domain)
    subordinates = list(session.scalars(select(Host).where(Host.parent_domain_id == domain.id)))
    users = {
        h.name: [d for d in host_used_by(session, h) if d != domain.name] for h in subordinates
    }
    in_use = {host: names for host, names in users.items() if names}
    if in_use and not force:
        raise HostInUse("subordinate hosts are used by other domains", hosts=in_use)

    used_hosts = [link.host for link in domain.nameservers]
    changed = {domain.name} | glue_owners(used_hosts)
    domain.nameservers = []
    session.flush()
    for host in subordinates:
        for other_name in users[host.name]:
            _drop_nameserver(ctx, other_name, host)
            changed.add(other_name)
        ctx.record("host.delete", host_name=host.name, before=host_view(session, host).to_event())
        session.delete(host)
    session.delete(domain)
    session.flush()
    delete_unused_external_hosts(ctx, [h for h in used_hosts if h not in subordinates])
    ctx.record(action, domain_name=domain.name, before=before.to_event())
    ctx.publisher.domains_changed(session, changed)


def _drop_nameserver(ctx: ServiceContext, domain_name: str, host: Host) -> None:
    other = find_domain(ctx, domain_name)
    assert other is not None
    before = domain_view(ctx, other)
    other.nameservers = [link for link in other.nameservers if link.host_id != host.id]
    for position, link in enumerate(other.nameservers):
        link.position = position
    ctx.session.flush()
    ctx.record(
        "domain.nameservers",
        domain_name=other.name,
        before=before.to_event(),
        after=domain_view(ctx, other).to_event(),
    )


class DomainService:
    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx
        self.session = ctx.session

    def check(self, raw_name: str) -> CheckResult:
        try:
            parsed = self.ctx.policy.parse_registrable(raw_name)
        except BadRequestError as err:
            return CheckResult(raw_name.strip(), False, err.code)
        existing = find_domain(self.ctx, parsed.name)
        if existing is not None and not self._past_grace(existing):
            return CheckResult(parsed.name, False, DomainExists.code)
        return CheckResult(parsed.name, True)

    def register(self, raw_name: str, owner: str, years: int | None = None) -> DomainView:
        parsed = self.ctx.policy.parse_registrable(raw_name)
        owner = _parse_owner(owner)
        years = self.ctx.settings.default_years if years is None else years
        _check_years(years)
        existing = find_domain(self.ctx, parsed.name)
        if existing is not None:
            if not self._past_grace(existing):
                raise DomainExists(name=parsed.name)
            remove_domain(self.ctx, existing, action="domain.purge", force=True)
        now = self.ctx.clock.now()
        domain = Domain(
            name=parsed.name,
            suffix=parsed.suffix,
            label=parsed.label,
            owner=owner,
            auth_code=secrets.token_urlsafe(12),
            created_at=now,
            expires_at=add_years(now, years),
            updated_at=now,
        )
        self.session.add(domain)
        self.session.flush()
        view = domain_view(self.ctx, domain)
        self.ctx.record("domain.register", domain_name=domain.name, after=view.to_event())
        self.ctx.publisher.domains_changed(self.session, {domain.name})
        return view

    def get(self, raw_name: str) -> DomainView:
        return domain_view(self.ctx, self.load(raw_name))

    def list_domains(
        self,
        prefix: str | None = None,
        owner: str | None = None,
        limit: int = DEFAULT_LIST_LIMIT,
        cursor: str | None = None,
    ) -> DomainPage:
        if not 1 <= limit <= MAX_LIST_LIMIT:
            raise ValidationFailed(f"limit must be 1..{MAX_LIST_LIMIT}", limit=limit)
        stmt = select(Domain).order_by(Domain.name).limit(limit + 1)
        if prefix:
            stmt = stmt.where(Domain.name.startswith(prefix.strip().lower(), autoescape=True))
        if owner is not None:
            stmt = stmt.where(Domain.owner == owner)
        if cursor:
            stmt = stmt.where(Domain.name > cursor)
        domains = list(self.session.scalars(stmt))
        page = domains[:limit]
        next_cursor = page[-1].name if len(domains) > limit else None
        return DomainPage([domain_view(self.ctx, d) for d in page], next_cursor)

    def renew(self, raw_name: str, years: int) -> DomainView:
        _check_years(years)
        domain = self.load(raw_name)
        new_expiry = add_years(domain.expires_at, years)
        if new_expiry > add_years(self.ctx.clock.now(), MAX_YEARS):
            raise RenewLimit(name=domain.name, expires_at=new_expiry.isoformat())
        before = domain_view(self.ctx, domain)
        domain.expires_at = new_expiry
        return self._changed(domain, "domain.renew", before)

    def delete(self, raw_name: str) -> None:
        """R-DOM-04."""
        remove_domain(self.ctx, self.load(raw_name), action="domain.delete", force=False)

    def update_status(
        self, raw_name: str, add: list[str] | None = None, remove: list[str] | None = None
    ) -> DomainView:
        """R-DOM-05: only clientHold, serverHold and pendingDelete can be set."""
        add_set, remove_set = set(add or ()), set(remove or ())
        unknown = (add_set | remove_set) - SETTABLE_STATUSES
        if unknown:
            raise InvalidStatus(statuses=sorted(unknown), allowed=sorted(SETTABLE_STATUSES))
        if add_set & remove_set:
            raise InvalidStatus(
                "status both added and removed", statuses=sorted(add_set & remove_set)
            )
        domain = self.load(raw_name)
        before = domain_view(self.ctx, domain)
        current = {s.status for s in domain.statuses}
        domain.statuses = [s for s in domain.statuses if s.status not in remove_set]
        domain.statuses += [DomainStatus(status=s) for s in sorted(add_set - current)]
        return self._changed(domain, "domain.status", before)

    def set_overrides(
        self,
        raw_name: str,
        propagation_delay: int | _Unset | None = UNSET,
        ns_ttl: int | _Unset | None = UNSET,
    ) -> DomainView:
        """Per-domain overrides; ``None`` clears one, ``UNSET`` leaves it unchanged."""
        domain = self.load(raw_name)
        before = domain_view(self.ctx, domain)
        if not isinstance(propagation_delay, _Unset):
            _check_int("propagation_delay", propagation_delay, maximum=None)
            domain.delay_override = propagation_delay
        if not isinstance(ns_ttl, _Unset):
            _check_int("ns_ttl", ns_ttl, maximum=MAX_TTL)
            domain.ns_ttl_override = ns_ttl
        return self._changed(domain, "domain.overrides", before)

    def load(self, raw_name: str) -> Domain:
        """Find a live domain; one past its grace period counts as purged (R-DOM-06)."""
        name = normalize_name(raw_name)
        domain = find_domain(self.ctx, name)
        if domain is None:
            raise DomainNotFound(name=name)
        if self._past_grace(domain):
            raise DomainPurged(name=name)
        return domain

    def _past_grace(self, domain: Domain) -> bool:
        return is_past_grace(domain, self.ctx.clock.now(), self.ctx.settings.expiry_grace_days)

    def _changed(self, domain: Domain, action: str, before: DomainView) -> DomainView:
        domain.updated_at = self.ctx.clock.now()
        self.session.flush()
        after = domain_view(self.ctx, domain)
        self.ctx.record(
            action, domain_name=domain.name, before=before.to_event(), after=after.to_event()
        )
        self.ctx.publisher.domains_changed(self.session, {domain.name})
        return after


def _parse_owner(owner: str) -> str:
    owner = owner.strip()
    if not owner or len(owner) > 255:
        raise ValidationFailed("owner must be 1..255 characters")
    return owner


def _check_years(years: int) -> None:
    """R-DOM-02."""
    if type(years) is not int or not 1 <= years <= MAX_YEARS:
        raise InvalidPeriod(f"years must be 1..{MAX_YEARS}", years=years)


def _check_int(field: str, value: int | None, maximum: int | None) -> None:
    if value is None:
        return
    if type(value) is not int or value < 0 or (maximum is not None and value > maximum):
        raise ValidationFailed(f"{field} must be a non-negative integer", field=field, value=value)
