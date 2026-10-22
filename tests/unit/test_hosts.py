import pytest

from plot.core.clock import FakeClock
from plot.core.errors import (
    HostAddrForbidden,
    HostAddrRequired,
    HostExists,
    HostInUse,
    HostNotFound,
    InvalidAddress,
    InvalidName,
)
from plot.db.models import Event, Host
from plot.services.context import ServiceContext
from plot.services.hosts import HostService, find_host
from tests.fakes import FakeDnsPublisher
from tests.helpers import actions, add_domain, use_as_ns


@pytest.fixture
def hosts(ctx: ServiceContext) -> HostService:
    return HostService(ctx)


def test_R_HOST_01_name_is_normalized(hosts: HostService) -> None:
    assert hosts.create("NS1.Other.NET.").name == "ns1.other.net"


@pytest.mark.parametrize("raw", ["localhost", "ns1", "", "ns_1.other.net", "-ns.other.net"])
def test_R_HOST_01_rejects_invalid_or_single_label(hosts: HostService, raw: str) -> None:
    with pytest.raises(InvalidName):
        hosts.create(raw)


def test_R_HOST_02_host_under_registered_domain_is_subordinate(
    hosts: HostService, ctx: ServiceContext, clock: FakeClock
) -> None:
    add_domain(ctx.session, clock, "shop.com")
    view = hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    assert (view.kind, view.parent_domain, view.ipv4) == (
        "subordinate",
        "shop.com",
        ["192.168.1.10"],
    )
    deep = hosts.create("a.b.ns.shop.com", ipv6=["2001:db8::1"])
    assert (deep.kind, deep.parent_domain) == ("subordinate", "shop.com")


def test_R_HOST_02_subordinate_requires_address(
    hosts: HostService, ctx: ServiceContext, clock: FakeClock
) -> None:
    add_domain(ctx.session, clock, "shop.com")
    with pytest.raises(HostAddrRequired):
        hosts.create("ns1.shop.com")


def test_R_HOST_02_parent_match_is_by_label_not_text(
    hosts: HostService, ctx: ServiceContext, clock: FakeClock
) -> None:
    add_domain(ctx.session, clock, "shop.com")
    assert hosts.create("ns1.myshop.com").kind == "external"


def test_R_HOST_03_external_host_has_no_address(hosts: HostService) -> None:
    view = hosts.create("ns1.other.net")
    assert (view.kind, view.parent_domain, view.ipv4, view.ipv6) == ("external", None, [], [])
    with pytest.raises(HostAddrForbidden):
        hosts.create("ns2.other.net", ipv4=["192.168.1.10"])


@pytest.mark.parametrize(
    ("ipv4", "ipv6"),
    [
        (["999.1.1.1"], []),
        (["2001:db8::1"], []),  # v6 in v4 list
        ([], ["192.168.1.1"]),  # v4 in v6 list
        (["0.0.0.0"], []),
        (["127.0.0.1"], []),
        (["224.0.0.1"], []),
        (["169.254.1.1"], []),
        ([], ["::"]),
        ([], ["::1"]),
        ([], ["ff02::1"]),
        ([], ["fe80::1"]),
        ([], ["::ffff:192.168.1.1"]),
        (["192.168.1.1", "192.168.1.1"], []),
    ],
)
def test_R_HOST_04_rejects_bad_addresses(
    hosts: HostService, ctx: ServiceContext, clock: FakeClock, ipv4: list[str], ipv6: list[str]
) -> None:
    add_domain(ctx.session, clock, "shop.com")
    with pytest.raises(InvalidAddress):
        hosts.create("ns1.shop.com", ipv4=ipv4, ipv6=ipv6)


def test_R_HOST_04_allows_private_and_public_and_canonicalizes(
    hosts: HostService, ctx: ServiceContext, clock: FakeClock
) -> None:
    add_domain(ctx.session, clock, "shop.com")
    view = hosts.create(
        "ns1.shop.com",
        ipv4=["10.0.0.1", "172.16.0.1", "192.168.1.175", "203.0.113.5"],
        ipv6=["2001:DB8:0:0::1", "fd00::1"],
    )
    assert view.ipv4 == ["10.0.0.1", "172.16.0.1", "192.168.1.175", "203.0.113.5"]
    assert view.ipv6 == ["2001:db8::1", "fd00::1"]


def test_R_HOST_05_update_replaces_given_families_and_republishes_parent(
    hosts: HostService, ctx: ServiceContext, clock: FakeClock, publisher: FakeDnsPublisher
) -> None:
    add_domain(ctx.session, clock, "shop.com")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"], ipv6=["2001:db8::1"])
    view = hosts.update("ns1.shop.com", ipv4=["192.168.1.20", "192.168.1.21"])
    assert view.ipv4 == ["192.168.1.20", "192.168.1.21"]
    assert view.ipv6 == ["2001:db8::1"]
    assert publisher.changed == {"shop.com"}
    view = hosts.update("ns1.shop.com", ipv6=[])
    assert view.ipv6 == []
    event = ctx.session.query(Event).filter_by(action="host.update").first()
    assert event is not None
    assert event.before == {
        "name": "ns1.shop.com",
        "kind": "subordinate",
        "parent_domain": "shop.com",
        "ipv4": ["192.168.1.10"],
        "ipv6": ["2001:db8::1"],
    }


def test_R_HOST_05_update_keeps_address_rules(
    hosts: HostService, ctx: ServiceContext, clock: FakeClock
) -> None:
    add_domain(ctx.session, clock, "shop.com")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    hosts.create("ns1.other.net")
    with pytest.raises(HostAddrRequired):
        hosts.update("ns1.shop.com", ipv4=[])
    with pytest.raises(HostAddrForbidden):
        hosts.update("ns1.other.net", ipv4=["192.168.1.10"])
    with pytest.raises(InvalidAddress):
        hosts.update("ns1.shop.com", ipv4=["127.0.0.1"])
    with pytest.raises(HostNotFound):
        hosts.update("ns9.shop.com", ipv4=["192.168.1.10"])


def test_R_HOST_06_host_used_as_ns_cannot_be_deleted(
    hosts: HostService, ctx: ServiceContext, clock: FakeClock
) -> None:
    add_domain(ctx.session, clock, "shop.com")
    other = add_domain(ctx.session, clock, "blog.com")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    host = find_host(ctx.session, "ns1.shop.com")
    assert host is not None
    use_as_ns(ctx.session, other, host)
    assert hosts.get("ns1.shop.com").used_by == ["blog.com"]
    with pytest.raises(HostInUse):
        hosts.delete("ns1.shop.com")


def test_R_HOST_06_unused_host_is_deleted(hosts: HostService, ctx: ServiceContext) -> None:
    hosts.create("ns1.other.net")
    hosts.delete("NS1.other.net.")
    assert ctx.session.query(Host).count() == 0
    with pytest.raises(HostNotFound):
        hosts.get("ns1.other.net")


def test_R_HOST_07_duplicate_host_name(hosts: HostService) -> None:
    hosts.create("ns1.other.net")
    with pytest.raises(HostExists):
        hosts.create("NS1.OTHER.NET.")


def test_R_DOM_07_host_changes_write_events(
    hosts: HostService, ctx: ServiceContext, clock: FakeClock
) -> None:
    add_domain(ctx.session, clock, "shop.com")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    hosts.update("ns1.shop.com", ipv4=["192.168.1.11"])
    hosts.delete("ns1.shop.com")
    assert actions(ctx.session) == ["host.create", "host.update", "host.delete"]


def test_list_hosts_sorted(hosts: HostService) -> None:
    hosts.create("ns2.other.net")
    hosts.create("ns1.other.net")
    assert [h.name for h in hosts.list()] == ["ns1.other.net", "ns2.other.net"]
