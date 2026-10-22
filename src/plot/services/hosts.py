"""Hosts (child nameservers): R-HOST-01..07 (SPEC §6.3)."""

import ipaddress
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from plot.core.errors import (
    HostAddrForbidden,
    HostAddrRequired,
    HostExists,
    HostInUse,
    HostNotFound,
    InvalidAddress,
    InvalidName,
)
from plot.core.names import name_and_ancestors, normalize_name
from plot.db.models import Domain, DomainNs, Host, HostAddr
from plot.services.context import ServiceContext

SUBORDINATE = "subordinate"
EXTERNAL = "external"


@dataclass(frozen=True)
class HostView:
    name: str
    kind: str
    parent_domain: str | None
    ipv4: list[str]
    ipv6: list[str]
    used_by: list[str]

    def to_event(self) -> dict[str, Any]:
        data = asdict(self)
        del data["used_by"]
        return data


def parse_host_name(raw: str) -> str:
    """R-HOST-01: a valid name (R-NAME-01/02) with at least two labels."""
    name = normalize_name(raw)
    if "." not in name:
        raise InvalidName("host name needs at least two labels", name=raw)
    return name


def parse_addresses(ipv4: Iterable[str], ipv6: Iterable[str]) -> list[tuple[int, str]]:
    """R-HOST-04: validate and canonicalize addresses as (family, address) pairs."""
    parsed: list[tuple[int, str]] = []
    for family, raws in ((4, ipv4), (6, ipv6)):
        for raw in raws:
            address = _parse_address(family, raw)
            if (family, address) in parsed:
                raise InvalidAddress("duplicate address", address=raw)
            parsed.append((family, address))
    return parsed


def _parse_address(family: int, raw: str) -> str:
    try:
        ip = ipaddress.IPv4Address(raw) if family == 4 else ipaddress.IPv6Address(raw)
    except ValueError:
        raise InvalidAddress(f"not an IPv{family} address", address=raw) from None
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        raise InvalidAddress("IPv4-mapped address; use the ipv4 list", address=raw)
    if ip.is_unspecified or ip.is_loopback or ip.is_multicast or ip.is_link_local:
        raise InvalidAddress(
            "unspecified, loopback, multicast and link-local addresses are not allowed",
            address=raw,
        )
    return str(ip)


def find_host(session: Session, name: str) -> Host | None:
    return session.scalars(select(Host).where(Host.name == name)).one_or_none()


def find_parent_domain(session: Session, name: str) -> Domain | None:
    """The registered domain ``name`` equals or sits below (longest match), if any."""
    candidates = name_and_ancestors(name)
    domains = session.scalars(select(Domain).where(Domain.name.in_(candidates))).all()
    return max(domains, key=lambda d: len(d.name), default=None)


def host_used_by(session: Session, host: Host) -> list[str]:
    stmt = (
        select(Domain.name)
        .join(DomainNs, DomainNs.domain_id == Domain.id)
        .where(DomainNs.host_id == host.id)
        .order_by(Domain.name)
    )
    return list(session.scalars(stmt))


def host_view(session: Session, host: Host) -> HostView:
    return HostView(
        name=host.name,
        kind=host.kind,
        parent_domain=host.parent_domain.name if host.parent_domain else None,
        ipv4=[a.address for a in host.addrs if a.family == 4],
        ipv6=[a.address for a in host.addrs if a.family == 6],
        used_by=host_used_by(session, host),
    )


def glue_owners(hosts: Iterable[Host]) -> set[str]:
    """Domains whose published glue depends on whether ``hosts`` are used as NS (R-PUB-03)."""
    return {h.parent_domain.name for h in hosts if h.parent_domain is not None}


def delete_unused_external_hosts(ctx: ServiceContext, hosts: Iterable[Host]) -> None:
    """R-NS-06: external hosts that no domain uses any more are removed automatically."""
    for host in hosts:
        if host.kind == EXTERNAL and not host_used_by(ctx.session, host):
            ctx.record(
                "host.delete", host_name=host.name, before=host_view(ctx.session, host).to_event()
            )
            ctx.session.delete(host)
    ctx.session.flush()


def _check_addresses(kind: str, addrs: Sequence[tuple[int, str]], name: str) -> None:
    if kind == SUBORDINATE and not addrs:
        raise HostAddrRequired(name=name)
    if kind == EXTERNAL and addrs:
        raise HostAddrForbidden(name=name)


class HostService:
    def __init__(self, ctx: ServiceContext) -> None:
        self.ctx = ctx
        self.session = ctx.session

    def get(self, raw_name: str) -> HostView:
        return host_view(self.session, self._load(raw_name))

    def list_hosts(self) -> list[HostView]:
        hosts = self.session.scalars(select(Host).order_by(Host.name))
        return [host_view(self.session, h) for h in hosts]

    def create(self, raw_name: str, ipv4: Iterable[str] = (), ipv6: Iterable[str] = ()) -> HostView:
        name = parse_host_name(raw_name)
        addrs = parse_addresses(ipv4, ipv6)
        if find_host(self.session, name) is not None:
            raise HostExists(name=name)
        parent = find_parent_domain(self.session, name)
        kind = SUBORDINATE if parent else EXTERNAL
        _check_addresses(kind, addrs, name)
        host = Host(name=name, kind=kind, parent_domain=parent, created_at=self.ctx.clock.now())
        host.addrs = [HostAddr(family=f, address=a) for f, a in addrs]
        self.session.add(host)
        self.session.flush()
        view = host_view(self.session, host)
        self.ctx.record("host.create", host_name=name, after=view.to_event())
        return view

    def update(
        self,
        raw_name: str,
        ipv4: Iterable[str] | None = None,
        ipv6: Iterable[str] | None = None,
    ) -> HostView:
        """R-HOST-05: replace the addresses of each family given; omitted families are kept."""
        host = self._load(raw_name)
        before = host_view(self.session, host)
        addrs = parse_addresses(
            before.ipv4 if ipv4 is None else ipv4,
            before.ipv6 if ipv6 is None else ipv6,
        )
        _check_addresses(host.kind, addrs, host.name)
        host.addrs = [HostAddr(family=f, address=a) for f, a in addrs]
        self.session.flush()
        after = host_view(self.session, host)
        self.ctx.record(
            "host.update", host_name=host.name, before=before.to_event(), after=after.to_event()
        )
        if host.parent_domain is not None:
            self.ctx.publisher.domains_changed(self.session, {host.parent_domain.name})
        return after

    def delete(self, raw_name: str) -> None:
        host = self._load(raw_name)
        view = host_view(self.session, host)
        if view.used_by:
            raise HostInUse(name=host.name, used_by=view.used_by)
        self.session.delete(host)
        self.session.flush()
        self.ctx.record("host.delete", host_name=host.name, before=view.to_event())

    def _load(self, raw_name: str) -> Host:
        name = parse_host_name(raw_name)
        host = find_host(self.session, name)
        if host is None:
            raise HostNotFound(name=name)
        return host
