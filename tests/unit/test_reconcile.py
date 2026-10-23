from typing import Any

from sqlalchemy.orm import Session

from plot.db.models import PublishedState
from plot.dns.pdns_client import root_rrsets
from plot.dns.projector import Snapshot
from plot.dns.reconcile import reconcile
from tests.conftest import T0

SHOP = {
    "nameservers": ["ns1.shop.com", "ns1.myhost.net"],
    "ttl": 300,
    "glue": {"ns1.shop.com": {"A": ["192.168.1.10"], "AAAA": []}},
}


class MemoryZone:
    """Zone '.' with pdns PATCH semantics (REPLACE / DELETE per name+type)."""

    def __init__(self) -> None:
        self.rrsets: dict[tuple[str, str], dict[str, Any]] = {}
        self.patches: list[list[dict[str, Any]]] = []
        self.root_ip: str | None = None

    def ensure_root_zone(self, root_ip: str) -> None:
        self.root_ip = root_ip
        self._apply(root_rrsets(root_ip))

    def zone_rrsets(self) -> list[dict[str, Any]]:
        return list(self.rrsets.values())

    def patch(self, rrsets: list[dict[str, Any]]) -> None:
        keys = [(r["name"], r["type"]) for r in rrsets]
        assert len(keys) == len(set(keys)), "pdns rejects duplicate RRsets in one PATCH"
        self.patches.append(rrsets)
        self._apply(rrsets)

    def _apply(self, rrsets: list[dict[str, Any]]) -> None:
        for r in rrsets:
            key = (r["name"], r["type"])
            if r["changetype"] == "DELETE":
                self.rrsets.pop(key, None)
            else:
                self.rrsets[key] = {k: v for k, v in r.items() if k != "changetype"}

    def put(self, name: str, rtype: str, ttl: int, contents: list[str]) -> None:
        self.rrsets[(name, rtype)] = {
            "name": name,
            "type": rtype,
            "ttl": ttl,
            "records": [{"content": c, "disabled": False} for c in contents],
        }

    def names(self) -> set[tuple[str, str]]:
        return set(self.rrsets)


def publish(session: Session, domain: str, snapshot: Snapshot) -> None:
    session.add(PublishedState(domain_name=domain, snapshot=snapshot, published_at=T0))
    session.flush()


ROOT = {(".", "SOA"), (".", "NS"), ("a.root-servers.net.", "A")}


def test_R_PUB_07_empty_pdns_is_rebuilt_from_published_state(session: Session) -> None:
    publish(session, "shop.com", SHOP)
    publish(session, "gone.com", None)
    zone = MemoryZone()
    assert reconcile(session, zone, "172.28.0.10") == ["shop.com"]
    assert zone.root_ip == "172.28.0.10"
    assert zone.names() == ROOT | {("shop.com.", "NS"), ("ns1.shop.com.", "A")}


def test_R_PUB_07_in_sync_zone_is_left_alone(session: Session) -> None:
    publish(session, "shop.com", SHOP)
    zone = MemoryZone()
    reconcile(session, zone, "172.28.0.10")
    zone.patches.clear()
    # record order inside an RRset is not drift
    zone.put("shop.com.", "NS", 300, ["ns1.myhost.net.", "ns1.shop.com."])
    assert reconcile(session, zone, "172.28.0.10") == []
    assert zone.patches == []


def test_R_PUB_07_drift_is_repaired(session: Session) -> None:
    publish(session, "shop.com", SHOP)
    zone = MemoryZone()
    zone.ensure_root_zone("172.28.0.10")
    zone.put("shop.com.", "NS", 60, ["ns9.evil.net."])  # wrong set and TTL
    zone.put("ns1.shop.com.", "A", 300, ["10.0.0.1"])  # wrong glue
    zone.put("old.shop.com.", "A", 300, ["10.0.0.2"])  # stale glue under the domain
    assert reconcile(session, zone, "172.28.0.10") == ["shop.com"]
    assert zone.rrsets[("shop.com.", "NS")]["ttl"] == 300
    assert zone.rrsets[("ns1.shop.com.", "A")]["records"] == [
        {"content": "192.168.1.10", "disabled": False}
    ]
    assert ("old.shop.com.", "A") not in zone.rrsets


def test_R_PUB_07_orphan_records_are_deleted(session: Session) -> None:
    publish(session, "shop.com", SHOP)
    zone = MemoryZone()
    reconcile(session, zone, "172.28.0.10")
    zone.put("hijack.com.", "NS", 300, ["ns1.evil.net."])
    zone.put("ns1.orphan.net.", "AAAA", 300, ["2001:db8::9"])
    assert reconcile(session, zone, "172.28.0.10") == ["hijack.com", "ns1.orphan.net"]
    assert zone.names() == ROOT | {("shop.com.", "NS"), ("ns1.shop.com.", "A")}


def test_R_PUB_07_domain_published_as_none_has_its_records_removed(session: Session) -> None:
    publish(session, "shop.com", None)
    zone = MemoryZone()
    zone.ensure_root_zone("172.28.0.10")
    zone.put("shop.com.", "NS", 300, ["ns1.x.net."])
    assert reconcile(session, zone, "172.28.0.10") == ["shop.com"]
    assert zone.names() == ROOT
