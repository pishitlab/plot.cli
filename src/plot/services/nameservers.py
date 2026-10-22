"""Nameserver set of a domain: R-NS-01..06 (SPEC §6.4)."""

from collections.abc import Sequence

from plot.core.errors import DuplicateNs, GlueRequired, HostNotFound, InvalidNsCount
from plot.core.names import is_within
from plot.core.tlds import MAX_NS
from plot.db.models import Domain, DomainNs, Host
from plot.services.context import ServiceContext
from plot.services.hosts import (
    EXTERNAL,
    SUBORDINATE,
    delete_unused_external_hosts,
    find_host,
    find_parent_domain,
    glue_owners,
    host_view,
    parse_host_name,
)


def replace_nameservers(ctx: ServiceContext, domain: Domain, raw_names: Sequence[str]) -> set[str]:
    """Replace the whole NS set of ``domain`` (R-NS-01) and return the domains to republish.

    Everything is validated before anything is written.
    """
    names = [parse_host_name(raw) for raw in raw_names]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        raise DuplicateNs(nameservers=duplicates)
    min_ns = ctx.policy.min_ns(domain.suffix)
    if names and not min_ns <= len(names) <= MAX_NS:
        raise InvalidNsCount(
            f"nameserver set must be empty or {min_ns}..{MAX_NS}", count=len(names), min=min_ns
        )
    resolved = [_resolve(ctx, domain, name) for name in names]

    session = ctx.session
    new_hosts = []
    for name, host in zip(names, resolved, strict=True):
        if host is None:
            # D-006 / R-NS-03: an external nameserver is created on first use.
            host = Host(name=name, kind=EXTERNAL, created_at=ctx.clock.now())
            session.add(host)
            session.flush()
            ctx.record("host.create", host_name=name, after=host_view(session, host).to_event())
        new_hosts.append(host)

    old_hosts = [link.host for link in domain.nameservers]
    domain.nameservers = []
    session.flush()
    domain.nameservers = [
        DomainNs(host_id=host.id, position=position, host=host)
        for position, host in enumerate(new_hosts)
    ]
    session.flush()
    delete_unused_external_hosts(ctx, [h for h in old_hosts if h not in new_hosts])
    return {domain.name} | glue_owners(old_hosts) | glue_owners(new_hosts)


def _resolve(ctx: ServiceContext, domain: Domain, name: str) -> Host | None:
    """The existing host for ``name``, or ``None`` when it may be created as external."""
    host = find_host(ctx.session, name)
    in_bailiwick = is_within(name, domain.name)
    if host is not None:
        if in_bailiwick and (host.kind != SUBORDINATE or not host.addrs):
            raise GlueRequired(nameserver=name)  # R-NS-04
        return host
    if in_bailiwick or find_parent_domain(ctx.session, name) is not None:
        raise HostNotFound("subordinate nameserver must be created first", name=name)  # R-NS-03
    return None
