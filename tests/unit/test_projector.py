from datetime import timedelta

import pytest

from plot.core.clock import FakeClock
from plot.dns.projector import project
from plot.services.context import ServiceContext
from plot.services.domains import DomainService
from plot.services.hosts import HostService
from plot.services.lifecycle import LifecycleService

NS_PAIR = ["ns1.myhost.net", "ns2.myhost.net"]


@pytest.fixture
def domains(ctx: ServiceContext) -> DomainService:
    return DomainService(ctx)


def snap(ctx: ServiceContext, name: str) -> object:
    return project(ctx.session, name, ctx.clock.now(), ctx.settings)


def test_R_PUB_01_snapshot_is_function_of_state_and_idempotent(
    domains: DomainService, ctx: ServiceContext
) -> None:
    domains.register("shop.com", owner="a", nameservers=NS_PAIR)
    first = snap(ctx, "shop.com")
    assert first == {"nameservers": NS_PAIR, "ttl": 300, "glue": {}}
    assert snap(ctx, "shop.com") == first
    domains.set_nameservers("shop.com", ["ns2.myhost.net", "ns1.myhost.net"])
    assert snap(ctx, "shop.com") == {
        "nameservers": ["ns2.myhost.net", "ns1.myhost.net"],
        "ttl": 300,
        "glue": {},
    }


def test_R_PUB_01_unknown_or_deleted_domain_projects_to_none(
    domains: DomainService, ctx: ServiceContext
) -> None:
    assert snap(ctx, "nope.com") is None
    domains.register("shop.com", owner="a", nameservers=NS_PAIR)
    domains.delete("shop.com")
    assert snap(ctx, "shop.com") is None


def test_R_PUB_02_no_delegation_without_nameservers(
    domains: DomainService, ctx: ServiceContext
) -> None:
    domains.register("shop.com", owner="a")
    assert snap(ctx, "shop.com") is None


@pytest.mark.parametrize("status", ["clientHold", "serverHold", "pendingDelete"])
def test_R_PUB_02_any_status_withdraws_delegation(
    domains: DomainService, ctx: ServiceContext, status: str
) -> None:
    domains.register("shop.com", owner="a", nameservers=NS_PAIR)
    domains.update_status("shop.com", add=[status])
    assert snap(ctx, "shop.com") is None
    domains.update_status("shop.com", remove=[status])
    assert snap(ctx, "shop.com") is not None


def test_R_PUB_02_expired_domain_not_delegated(
    domains: DomainService, ctx: ServiceContext, clock: FakeClock
) -> None:
    domains.register("shop.com", owner="a", nameservers=NS_PAIR)
    LifecycleService(ctx).expire_now("shop.com")
    assert snap(ctx, "shop.com") is None
    domains.renew("shop.com", 1)
    assert snap(ctx, "shop.com") is not None
    clock.advance(timedelta(days=800))
    assert snap(ctx, "shop.com") is None


def test_R_PUB_03_glue_only_for_used_subordinate_hosts(
    domains: DomainService, ctx: ServiceContext
) -> None:
    hosts = HostService(ctx)
    domains.register("shop.com", owner="a")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"], ipv6=["2001:db8::1"])
    hosts.create("ns2.shop.com", ipv4=["192.168.1.11"])
    hosts.create("spare.shop.com", ipv4=["192.168.1.12"])
    domains.set_nameservers("shop.com", ["ns1.shop.com", "ns2.shop.com"])
    assert snap(ctx, "shop.com") == {
        "nameservers": ["ns1.shop.com", "ns2.shop.com"],
        "ttl": 300,
        "glue": {
            "ns1.shop.com": {"A": ["192.168.1.10"], "AAAA": ["2001:db8::1"]},
            "ns2.shop.com": {"A": ["192.168.1.11"], "AAAA": []},
        },
    }


def test_R_PUB_03_glue_published_with_parent_when_used_by_other_domain(
    domains: DomainService, ctx: ServiceContext
) -> None:
    hosts = HostService(ctx)
    domains.register("shop.com", owner="a", nameservers=NS_PAIR)
    domains.register("blog.com", owner="a")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    assert snap(ctx, "shop.com") == {"nameservers": NS_PAIR, "ttl": 300, "glue": {}}
    domains.set_nameservers("blog.com", ["ns1.shop.com", "ns1.myhost.net"])
    glue = {"ns1.shop.com": {"A": ["192.168.1.10"], "AAAA": []}}
    assert snap(ctx, "shop.com") == {"nameservers": NS_PAIR, "ttl": 300, "glue": glue}
    assert snap(ctx, "blog.com") == {
        "nameservers": ["ns1.shop.com", "ns1.myhost.net"],
        "ttl": 300,
        "glue": {},
    }
    # parent not delegated -> its glue disappears even though blog.com still uses it
    domains.update_status("shop.com", add=["serverHold"])
    assert snap(ctx, "shop.com") is None


def test_R_PUB_04_ttl_override_or_setting(domains: DomainService, ctx: ServiceContext) -> None:
    domains.register("shop.com", owner="a", nameservers=NS_PAIR)
    ctx.settings = ctx.settings.model_copy(update={"ns_ttl": 120})
    assert snap(ctx, "shop.com") == {"nameservers": NS_PAIR, "ttl": 120, "glue": {}}
    domains.set_overrides("shop.com", ns_ttl=0)
    assert snap(ctx, "shop.com") == {"nameservers": NS_PAIR, "ttl": 0, "glue": {}}
