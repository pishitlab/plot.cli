import pytest

from plot.core.errors import (
    DomainNotFound,
    DuplicateNs,
    GlueRequired,
    HostNotFound,
    InvalidName,
    InvalidNsCount,
)
from plot.db.models import Event, Host
from plot.services.context import ServiceContext
from plot.services.domains import DomainService
from plot.services.hosts import HostService, find_host
from tests.fakes import FakeDnsPublisher
from tests.helpers import actions

NS_PAIR = ["ns1.myhost.net", "ns2.myhost.net"]


@pytest.fixture
def domains(ctx: ServiceContext) -> DomainService:
    return DomainService(ctx)


@pytest.fixture
def hosts(ctx: ServiceContext) -> HostService:
    return HostService(ctx)


def _host_names(ctx: ServiceContext) -> list[str]:
    return sorted(h.name for h in ctx.session.query(Host))


def test_R_NS_01_put_replaces_whole_set_in_order(domains: DomainService) -> None:
    domains.register("shop.com", owner="alice")
    assert domains.set_nameservers("shop.com", NS_PAIR).nameservers == NS_PAIR
    new = ["ns3.other.net", "ns1.myhost.net", "ns2.other.net"]
    assert domains.set_nameservers("shop.com", new).nameservers == new


@pytest.mark.parametrize("count", [1, 14])
def test_R_NS_01_count_must_be_zero_or_min_to_13(domains: DomainService, count: int) -> None:
    domains.register("shop.com", owner="alice")
    with pytest.raises(InvalidNsCount):
        domains.set_nameservers("shop.com", [f"ns{i}.other.net" for i in range(count)])


def test_R_NS_01_thirteen_is_the_maximum(domains: DomainService) -> None:
    domains.register("shop.com", owner="alice")
    names = [f"ns{i}.other.net" for i in range(13)]
    assert len(domains.set_nameservers("shop.com", names).nameservers) == 13


def test_R_NS_01_min_ns_comes_from_suffix(domains: DomainService) -> None:
    # conftest policy: "th" has min_ns 1, "com" the default 2
    domains.register("shop.th", owner="alice")
    assert domains.set_nameservers("shop.th", ["ns1.other.net"]).nameservers == ["ns1.other.net"]


def test_R_NS_01_register_with_nameservers_applies_same_rules(
    domains: DomainService, publisher: FakeDnsPublisher
) -> None:
    view = domains.register(
        "shop.com", owner="alice", nameservers=["NS1.MyHost.NET.", "ns2.myhost.net"]
    )
    assert view.nameservers == NS_PAIR
    assert publisher.changed == {"shop.com"}
    with pytest.raises(InvalidNsCount):
        domains.register("blog.com", owner="alice", nameservers=["ns1.myhost.net"])


def test_R_NS_02_duplicates_after_normalization(domains: DomainService) -> None:
    domains.register("shop.com", owner="alice")
    with pytest.raises(DuplicateNs):
        domains.set_nameservers("shop.com", ["ns1.myhost.net", "NS1.MYHOST.NET."])


def test_R_NS_02_invalid_ns_name(domains: DomainService) -> None:
    domains.register("shop.com", owner="alice")
    with pytest.raises(InvalidName):
        domains.set_nameservers("shop.com", ["ns1.myhost.net", "ns_2.myhost.net"])


def test_R_NS_03_external_hosts_created_automatically(
    domains: DomainService, ctx: ServiceContext
) -> None:
    domains.register("shop.com", owner="alice")
    domains.set_nameservers("shop.com", NS_PAIR)
    for name in NS_PAIR:
        host = find_host(ctx.session, name)
        assert host is not None and host.kind == "external" and host.addrs == []


def test_R_NS_03_subordinate_ns_must_exist(domains: DomainService) -> None:
    domains.register("shop.com", owner="alice")
    domains.register("blog.com", owner="alice")
    with pytest.raises(HostNotFound):
        domains.set_nameservers("blog.com", ["ns1.shop.com", "ns1.myhost.net"])
    with pytest.raises(HostNotFound):
        domains.set_nameservers("shop.com", ["ns1.shop.com", "ns1.myhost.net"])


def test_R_NS_03_existing_subordinate_host_of_other_domain_is_used(
    domains: DomainService, hosts: HostService
) -> None:
    domains.register("shop.com", owner="alice")
    domains.register("blog.com", owner="alice")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    view = domains.set_nameservers("blog.com", ["ns1.shop.com", "ns1.myhost.net"])
    assert view.nameservers == ["ns1.shop.com", "ns1.myhost.net"]


def test_R_NS_04_in_bailiwick_ns_with_glue(
    domains: DomainService, hosts: HostService, publisher: FakeDnsPublisher
) -> None:
    domains.register("shop.com", owner="alice")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    hosts.create("ns2.shop.com", ipv6=["2001:db8::2"])
    publisher.reset()
    view = domains.set_nameservers("shop.com", ["ns1.shop.com", "ns2.shop.com"])
    assert view.nameservers == ["ns1.shop.com", "ns2.shop.com"]
    assert publisher.changed == {"shop.com"}


def test_R_NS_04_in_bailiwick_host_without_glue_rejected(
    domains: DomainService, hosts: HostService
) -> None:
    # ns1.shop.com was created as external before shop.com existed (no re-classification)
    hosts.create("ns1.shop.com")
    domains.register("shop.com", owner="alice")
    with pytest.raises(GlueRequired):
        domains.set_nameservers("shop.com", ["ns1.shop.com", "ns1.myhost.net"])


def test_R_NS_05_empty_set_keeps_domain_without_delegation(
    domains: DomainService, publisher: FakeDnsPublisher
) -> None:
    domains.register("shop.com", owner="alice", nameservers=NS_PAIR)
    publisher.reset()
    view = domains.set_nameservers("shop.com", [])
    assert view.nameservers == []
    assert domains.get("shop.com").name == "shop.com"
    assert publisher.changed == {"shop.com"}


def test_R_NS_06_unused_external_hosts_removed_after_replace(
    domains: DomainService, ctx: ServiceContext
) -> None:
    domains.register("shop.com", owner="alice", nameservers=NS_PAIR)
    domains.register("blog.com", owner="alice", nameservers=["ns1.myhost.net", "ns9.other.net"])
    domains.set_nameservers("shop.com", ["ns1.other.net", "ns2.other.net"])
    # ns2.myhost.net is unused now; ns1.myhost.net is still used by blog.com
    assert _host_names(ctx) == [
        "ns1.myhost.net",
        "ns1.other.net",
        "ns2.other.net",
        "ns9.other.net",
    ]
    domains.set_nameservers("blog.com", [])
    assert _host_names(ctx) == ["ns1.other.net", "ns2.other.net"]


def test_R_NS_06_subordinate_hosts_are_kept(
    domains: DomainService, hosts: HostService, ctx: ServiceContext
) -> None:
    domains.register("shop.com", owner="alice")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    hosts.create("ns2.shop.com", ipv4=["192.168.1.11"])
    domains.set_nameservers("shop.com", ["ns1.shop.com", "ns2.shop.com"])
    domains.set_nameservers("shop.com", [])
    assert _host_names(ctx) == ["ns1.shop.com", "ns2.shop.com"]


def test_ns_change_republishes_glue_owner(
    domains: DomainService, hosts: HostService, publisher: FakeDnsPublisher
) -> None:
    domains.register("shop.com", owner="alice")
    domains.register("blog.com", owner="alice")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    publisher.reset()
    domains.set_nameservers("blog.com", ["ns1.shop.com", "ns1.myhost.net"])
    assert publisher.calls[-1] == frozenset({"blog.com", "shop.com"})
    domains.set_nameservers("blog.com", NS_PAIR)
    assert publisher.calls[-1] == frozenset({"blog.com", "shop.com"})


def test_failed_change_leaves_nothing_written(domains: DomainService, ctx: ServiceContext) -> None:
    domains.register("shop.com", owner="alice", nameservers=NS_PAIR)
    ctx.session.commit()
    with pytest.raises(HostNotFound):
        domains.set_nameservers("shop.com", ["ns1.new.net", "ns1.shop.com"])
    assert _host_names(ctx) == NS_PAIR
    assert domains.get("shop.com").nameservers == NS_PAIR


def test_set_nameservers_unknown_domain(domains: DomainService) -> None:
    with pytest.raises(DomainNotFound):
        domains.set_nameservers("nope.com", NS_PAIR)


def test_R_DOM_07_nameserver_changes_write_events(
    domains: DomainService, ctx: ServiceContext
) -> None:
    domains.register("shop.com", owner="alice")
    domains.set_nameservers("shop.com", NS_PAIR)
    domains.set_nameservers("shop.com", [])
    assert actions(ctx.session) == [
        "domain.register",
        "host.create",
        "host.create",
        "domain.nameservers",
        "host.delete",
        "host.delete",
        "domain.nameservers",
    ]
    last = ctx.session.query(Event).filter_by(action="domain.nameservers").all()[-1]
    assert last.before is not None and last.after is not None
    assert (last.before["nameservers"], last.after["nameservers"]) == (NS_PAIR, [])
