"""Seed the provider domain used by customer domains as nameservers (SPEC §17 step 4)."""

from collections.abc import Sequence

from plot.core.errors import HostAddrForbidden, ValidationFailed
from plot.services.context import ServiceContext
from plot.services.domains import MAX_YEARS, DomainService, DomainView, find_domain
from plot.services.hosts import EXTERNAL, HostService, find_host

SEED_OWNER = "seed"


def seed_provider(ctx: ServiceContext, raw_domain: str, ns_ips: Sequence[str]) -> DomainView:
    """Idempotently register ``raw_domain`` (kept by /admin/reset) with child nameservers
    ns1, ns2, ... carrying ``ns_ips`` as glue, and delegate the domain to them."""
    if not ns_ips:
        raise ValidationFailed("at least one nameserver address is required")
    domains = DomainService(ctx)
    hosts = HostService(ctx)
    name = ctx.policy.parse_registrable(raw_domain).name
    domain = find_domain(ctx, name)
    if domain is None:
        domains.register(name, owner=SEED_OWNER, years=MAX_YEARS)
        domain = find_domain(ctx, name)
        assert domain is not None
    domain.seed = True
    nameservers = []
    for index, ip in enumerate(ns_ips, start=1):
        host_name = f"ns{index}.{name}"
        family = "ipv6" if ":" in ip else "ipv4"
        existing = find_host(ctx.session, host_name)
        if existing is None:
            hosts.create(host_name, **{family: [ip]})
        elif existing.kind == EXTERNAL:
            # Hosts are never re-classified (SPEC §1.3): it was used as NS before the seed.
            raise HostAddrForbidden(
                f"{host_name} already exists as an external host; reset or delete the "
                "domains using it, then seed again",
                name=host_name,
                used_by=hosts.get(host_name).used_by,
            )
        else:
            hosts.update(
                host_name,
                ipv4=[ip] if family == "ipv4" else [],
                ipv6=[ip] if family == "ipv6" else [],
            )
        nameservers.append(host_name)
    return domains.set_nameservers(name, nameservers)
