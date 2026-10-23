"""Startup reconcile (R-PUB-07): make zone ``.`` match ``published_state`` again.

Pending changes need no extra work: their ``apply_at`` is absolute, so the publish worker
applies overdue ones on its first pass after a restart.
"""

from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from plot.core.names import is_within
from plot.db.models import PublishedState
from plot.dns.pdns_client import ROOT_NS, fqdn, rrset_changes
from plot.dns.projector import Snapshot

RRset = dict[str, Any]
# (name, type, ttl, sorted contents): order of records inside an RRset carries no meaning
Canonical = frozenset[tuple[str, str, int, tuple[str, ...]]]


class ZoneAccess(Protocol):
    def ensure_root_zone(self, root_ip: str) -> None: ...
    def zone_rrsets(self) -> list[RRset]: ...
    def patch(self, rrsets: list[RRset]) -> None: ...


def _bare(name: str) -> str:
    return name[:-1] if name.endswith(".") and name != "." else name


def _is_registry_own(rrset: RRset) -> bool:
    return rrset["name"] == "." or _bare(rrset["name"]) == ROOT_NS


def desired_rrsets(domain: str, snapshot: Snapshot) -> Canonical:
    return frozenset(
        (r["name"], r["type"], r["ttl"], tuple(sorted(rec["content"] for rec in r["records"])))
        for r in rrset_changes(domain, None, snapshot)
        if r["changetype"] == "REPLACE"
    )


def actual_rrsets(domain: str, zone: list[RRset]) -> Canonical:
    return frozenset(
        (r["name"], r["type"], r["ttl"], tuple(sorted(rec["content"] for rec in r["records"])))
        for r in zone
        if not _is_registry_own(r)
        and (
            (r["type"] == "NS" and _bare(r["name"]) == domain)
            or (r["type"] in ("A", "AAAA") and is_within(_bare(r["name"]), domain))
        )
    )


def reconcile(session: Session, zone: ZoneAccess, root_ip: str) -> list[str]:
    """Rewrite drifted domains and delete records no domain owns; returns the names fixed."""
    zone.ensure_root_zone(root_ip)
    current = zone.zone_rrsets()
    published = {
        state.domain_name: state.snapshot for state in session.scalars(select(PublishedState))
    }
    fixed: list[str] = []
    for domain, snapshot in sorted(published.items()):
        if actual_rrsets(domain, current) != desired_rrsets(domain, snapshot):
            replace = [
                r for r in rrset_changes(domain, None, snapshot) if r["changetype"] == "REPLACE"
            ]
            keep = {(r["name"], r["type"]) for r in replace}
            stale = [
                _delete(r)
                for r in current
                if _owned_by(r, domain) and (fqdn(_bare(r["name"])), r["type"]) not in keep
            ]
            zone.patch(stale + replace)
            fixed.append(domain)
    orphans = [
        r
        for r in current
        if not _is_registry_own(r)
        and r["type"] in ("NS", "A", "AAAA")
        and not any(_owned_by(r, d) for d in published)
    ]
    if orphans:
        zone.patch([_delete(r) for r in orphans])
        fixed.extend(sorted({_bare(r["name"]) for r in orphans}))
    return fixed


def _owned_by(rrset: RRset, domain: str) -> bool:
    name = _bare(rrset["name"])
    if rrset["type"] == "NS":
        return name == domain
    return rrset["type"] in ("A", "AAAA") and is_within(name, domain)


def _delete(rrset: RRset) -> RRset:
    return {"name": fqdn(_bare(rrset["name"])), "type": rrset["type"], "changetype": "DELETE"}
