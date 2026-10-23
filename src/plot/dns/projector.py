"""DB state -> what the registry zone must contain for one domain (R-PUB-01..04, SPEC §6.5).

A snapshot is JSON-serializable and fully determines the domain's RRsets in zone ``.``::

    {"nameservers": ["ns1.shop.com", ...],          # NS <domain>, in configured order
     "ttl": 300,                                    # TTL of NS and glue (R-PUB-04)
     "glue": {"ns1.shop.com": {"A": [...], "AAAA": [...]}}}

``None`` means the domain must have no RRsets at all.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from plot.core.settings import RuntimeSettings
from plot.db.models import Domain, DomainNs, Host
from plot.services.domains import is_expired

Snapshot = dict[str, Any] | None


def delegation_published(domain: Domain, now: datetime) -> bool:
    """R-PUB-02: no status set, not expired and a non-empty NS set."""
    return not domain.statuses and not is_expired(domain, now) and bool(domain.nameservers)


def project(
    session: Session, domain_name: str, now: datetime, settings: RuntimeSettings
) -> Snapshot:
    """Snapshot of ``domain_name`` from the current state of ``session`` (R-PUB-01)."""
    domain = session.scalars(select(Domain).where(Domain.name == domain_name)).one_or_none()
    if domain is None or not delegation_published(domain, now):
        return None
    ttl = settings.ns_ttl if domain.ns_ttl_override is None else domain.ns_ttl_override
    used = exists().where(DomainNs.host_id == Host.id)
    glue_hosts = session.scalars(
        select(Host).where(Host.parent_domain_id == domain.id, used).order_by(Host.name)
    )
    glue = {
        host.name: {
            "A": [a.address for a in host.addrs if a.family == 4],
            "AAAA": [a.address for a in host.addrs if a.family == 6],
        }
        for host in glue_hosts
    }
    return {
        "nameservers": [link.host.name for link in domain.nameservers],
        "ttl": ttl,
        "glue": glue,
    }
