from datetime import timedelta

import pytest

from plot.core.clock import FakeClock
from plot.core.errors import DomainNotFound, DomainPurged
from plot.db.models import Event
from plot.services.context import ServiceContext
from plot.services.domains import DomainService
from plot.services.hosts import HostService, find_host
from plot.services.lifecycle import LifecycleService
from tests.conftest import T0
from tests.fakes import FakeDnsPublisher

NS_PAIR = ["ns1.myhost.net", "ns2.myhost.net"]
YEAR = timedelta(days=365)  # 2026 is not a leap year
GRACE = timedelta(days=30)


@pytest.fixture
def domains(ctx: ServiceContext) -> DomainService:
    return DomainService(ctx)


@pytest.fixture
def lifecycle(ctx: ServiceContext) -> LifecycleService:
    return LifecycleService(ctx)


def test_R_DOM_06_expired_is_derived_from_now(domains: DomainService, clock: FakeClock) -> None:
    domains.register("shop.com", owner="alice")
    clock.set(T0 + YEAR)
    assert not domains.get("shop.com").expired  # now == expires_at is not expired
    clock.advance(timedelta(microseconds=1))
    assert domains.get("shop.com").expired


def test_R_DOM_06_renew_within_grace_restores(domains: DomainService, clock: FakeClock) -> None:
    domains.register("shop.com", owner="alice")
    clock.set(T0 + YEAR + GRACE)  # last moment of the grace period
    view = domains.renew("shop.com", 1)
    assert not view.expired
    assert view.expires_at == T0.replace(year=2028)


def test_R_DOM_06_past_grace_counts_as_purged(domains: DomainService, clock: FakeClock) -> None:
    domains.register("shop.com", owner="alice")
    clock.set(T0 + YEAR + GRACE + timedelta(seconds=1))
    with pytest.raises(DomainPurged):
        domains.renew("shop.com", 1)
    with pytest.raises(DomainPurged):
        domains.get("shop.com")
    assert domains.check("shop.com").available


def test_R_DOM_06_grace_days_come_from_settings(ctx: ServiceContext, clock: FakeClock) -> None:
    ctx.settings = ctx.settings.model_copy(update={"expiry_grace_days": 0})
    domains = DomainService(ctx)
    domains.register("shop.com", owner="alice")
    clock.set(T0 + YEAR + timedelta(seconds=1))
    with pytest.raises(DomainPurged):
        domains.get("shop.com")


def test_R_DOM_06_lifecycle_purges_and_frees_name(
    domains: DomainService,
    lifecycle: LifecycleService,
    clock: FakeClock,
    ctx: ServiceContext,
    publisher: FakeDnsPublisher,
) -> None:
    domains.register("shop.com", owner="alice", nameservers=NS_PAIR)
    domains.register("keep.com", owner="alice", years=2)
    clock.set(T0 + YEAR + GRACE + timedelta(seconds=1))
    publisher.reset()
    result = lifecycle.run(since=T0 + YEAR + GRACE)
    assert result.purged == ["shop.com"]
    assert publisher.changed == {"shop.com"}
    with pytest.raises(DomainNotFound):
        domains.get("shop.com")
    assert find_host(ctx.session, "ns1.myhost.net") is None  # R-NS-06 on purge
    assert domains.register("shop.com", owner="bob").owner == "bob"
    assert ctx.session.query(Event).filter_by(action="domain.purge").count() == 1


def test_R_DOM_06_register_purges_lapsed_domain_without_waiting_for_job(
    domains: DomainService, clock: FakeClock, ctx: ServiceContext
) -> None:
    domains.register("shop.com", owner="alice")
    clock.set(T0 + YEAR + GRACE + timedelta(days=1))
    assert domains.register("shop.com", owner="bob").owner == "bob"
    actions = [e.action for e in ctx.session.query(Event).order_by(Event.id)]
    assert actions == ["domain.register", "domain.purge", "domain.register"]


def test_R_DOM_06_purge_detaches_subordinate_hosts_used_elsewhere(
    domains: DomainService,
    lifecycle: LifecycleService,
    clock: FakeClock,
    ctx: ServiceContext,
    publisher: FakeDnsPublisher,
) -> None:
    domains.register("shop.com", owner="alice")
    domains.register("blog.com", owner="alice", years=5)
    HostService(ctx).create("ns1.shop.com", ipv4=["192.168.1.10"])
    domains.set_nameservers("blog.com", ["ns1.shop.com", *NS_PAIR])
    clock.set(T0 + YEAR + GRACE + timedelta(days=1))
    publisher.reset()
    assert lifecycle.run().purged == ["shop.com"]
    assert domains.get("blog.com").nameservers == NS_PAIR
    assert find_host(ctx.session, "ns1.shop.com") is None
    assert publisher.changed == {"shop.com", "blog.com"}


def test_R_DOM_06_lifecycle_republishes_newly_expired(
    domains: DomainService,
    lifecycle: LifecycleService,
    clock: FakeClock,
    publisher: FakeDnsPublisher,
) -> None:
    domains.register("a.com", owner="x")
    domains.register("b.com", owner="x", years=2)
    clock.set(T0 + YEAR + timedelta(days=1))
    publisher.reset()
    first = lifecycle.run()
    assert first.expired == ["a.com"] and first.purged == []
    assert publisher.changed == {"a.com"}
    publisher.reset()
    second = lifecycle.run(since=clock.now())
    assert second.expired == [] and publisher.calls == []
    since = clock.now()
    clock.set(T0 + 2 * YEAR + timedelta(days=2))
    assert lifecycle.run(since=since).expired == ["b.com"]


def test_expire_now_moves_expiry_into_past(
    domains: DomainService,
    lifecycle: LifecycleService,
    clock: FakeClock,
    publisher: FakeDnsPublisher,
    ctx: ServiceContext,
) -> None:
    domains.register("shop.com", owner="alice", years=3)
    publisher.reset()
    view = lifecycle.expire_now("shop.com")
    assert view.expired
    assert view.expires_at < clock.now()
    assert publisher.changed == {"shop.com"}
    renewed = domains.renew("shop.com", 1)  # S10: renew within grace brings it back
    assert not renewed.expired
    assert ctx.session.query(Event).filter_by(action="domain.expire_now").count() == 1
