import threading
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from plot.core.clock import FakeClock
from plot.core.settings import RuntimeSettings
from plot.core.tlds import NamePolicy
from plot.db.models import Base
from plot.db.session import make_engine, make_session_factory
from plot.dns.projector import Snapshot
from plot.dns.publisher import Publisher, PublishWorker
from plot.services.context import ServiceContext
from plot.services.domains import DomainService, dns_visible
from plot.services.events import RequestContext
from plot.services.settings import load_settings, update_settings
from tests.conftest import T0
from tests.fakes import FakeResolverControl

NS_PAIR = ["ns1.myhost.net", "ns2.myhost.net"]
DEFAULTS = RuntimeSettings()


class FakeRegistry:
    def __init__(self) -> None:
        self.zone: dict[str, Snapshot] = {}
        self.down = False
        self.calls = 0

    def ensure_root_zone(self, root_ip: str) -> None:
        pass

    def zone_rrsets(self) -> list[dict[str, Any]]:
        return []

    def patch(self, rrsets: list[dict[str, Any]]) -> None:
        pass

    def apply(self, domain: str, old: Snapshot, new: Snapshot) -> None:
        self.calls += 1
        if self.down:
            raise ConnectionError("pdns down")
        if new is None:
            self.zone.pop(domain, None)
        else:
            self.zone[domain] = new


@pytest.fixture
def sessions() -> sessionmaker[Session]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


@pytest.fixture
def registry() -> FakeRegistry:
    return FakeRegistry()


@pytest.fixture
def publisher(registry: FakeRegistry, clock: FakeClock) -> Publisher:
    return Publisher(
        registry,
        FakeResolverControl(),
        clock,
        lambda session: load_settings(session, DEFAULTS),
        root_ip="172.28.0.10",
    )


Change = Callable[[DomainService], object]


def change(
    sessions: sessionmaker[Session],
    clock: FakeClock,
    publisher: Publisher,
    policy: NamePolicy,
    fn: Change,
) -> None:
    with sessions.begin() as session:
        ctx = ServiceContext(
            session,
            clock,
            publisher,
            policy,
            load_settings(session, DEFAULTS),
            RequestContext("test", "r"),
        )
        fn(DomainService(ctx))


def test_change_is_scheduled_then_applied(
    sessions: sessionmaker[Session],
    clock: FakeClock,
    publisher: Publisher,
    registry: FakeRegistry,
    policy: NamePolicy,
) -> None:
    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.register("shop.com", "a", nameservers=NS_PAIR),
    )
    assert registry.zone == {}
    with sessions.begin() as session:
        assert publisher.apply_due(session).applied == ["shop.com"]
    assert registry.zone["shop.com"] == {"nameservers": NS_PAIR, "ttl": 300, "glue": {}}


def test_delay_keeps_old_delegation_visible_until_due(
    sessions: sessionmaker[Session],
    clock: FakeClock,
    publisher: Publisher,
    registry: FakeRegistry,
    policy: NamePolicy,
) -> None:
    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.register("shop.com", "a", nameservers=NS_PAIR),
    )
    with sessions.begin() as session:
        publisher.apply_due(session)
        update_settings(
            session, clock, RequestContext("t", "r"), DEFAULTS, {"propagation_delay": 20}
        )
    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.set_nameservers("shop.com", ["ns1.b.net", "ns2.b.net"]),
    )
    clock.advance(19)
    with sessions.begin() as session:
        assert publisher.apply_due(session).applied == []
        ctx = ServiceContext(session, clock, publisher, policy, DEFAULTS, RequestContext("t", "r"))
        visible = dns_visible(ctx, "shop.com")
        assert visible.nameservers == NS_PAIR
        assert visible.pending == [T0 + timedelta(seconds=20)]
    clock.advance(1)
    with sessions.begin() as session:
        assert publisher.apply_due(session).applied == ["shop.com"]
    assert registry.zone["shop.com"]["nameservers"] == ["ns1.b.net", "ns2.b.net"]  # type: ignore[index]


def test_hold_and_delete_remove_delegation(
    sessions: sessionmaker[Session],
    clock: FakeClock,
    publisher: Publisher,
    registry: FakeRegistry,
    policy: NamePolicy,
) -> None:
    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.register("shop.com", "a", nameservers=NS_PAIR),
    )
    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.update_status("shop.com", add=["serverHold"]),
    )
    with sessions.begin() as session:
        publisher.apply_due(session)
    assert "shop.com" not in registry.zone
    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.update_status("shop.com", remove=["serverHold"]),
    )
    with sessions.begin() as session:
        publisher.apply_due(session)
    assert "shop.com" in registry.zone
    change(sessions, clock, publisher, policy, lambda d: d.delete("shop.com"))
    with sessions.begin() as session:
        publisher.apply_due(session)
    assert registry.zone == {}


def test_R_PUB_09_registry_down_keeps_changes_and_worker_backs_off(
    sessions: sessionmaker[Session],
    clock: FakeClock,
    publisher: Publisher,
    registry: FakeRegistry,
    policy: NamePolicy,
) -> None:
    registry.down = True
    # the API-side change still succeeds
    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.register("shop.com", "a", nameservers=NS_PAIR),
    )
    worker = PublishWorker(sessions, publisher, interval=0.5)
    assert [worker.run_once() for _ in range(3)] == [1, 2, 4]
    assert not worker.healthy
    registry.down = False
    assert worker.run_once() == 0.5
    assert worker.healthy
    assert "shop.com" in registry.zone


def test_worker_thread_applies_and_runs_tick_hook(
    sessions: sessionmaker[Session],
    clock: FakeClock,
    publisher: Publisher,
    registry: FakeRegistry,
    policy: NamePolicy,
) -> None:
    ticks: list[int] = []
    third_tick = threading.Event()

    def tick() -> None:
        ticks.append(1)
        if len(ticks) == 1:
            raise RuntimeError("hook failures are logged, not fatal")
        if len(ticks) == 3:  # the passes after the first two ticks have completed
            third_tick.set()

    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.register("shop.com", "a", nameservers=NS_PAIR),
    )
    worker = PublishWorker(sessions, publisher, interval=0.01, on_tick=tick)
    worker.start()
    assert third_tick.wait(timeout=5), "worker loop did not run"
    worker.stop()
    assert "shop.com" in registry.zone


class FlakyResolver(FakeResolverControl):
    def flush(self, domain_name: str | None = None) -> None:
        super().flush(domain_name)
        raise ConnectionError("unbound-control down")


@pytest.mark.parametrize("flush_on_apply", [True, False])
def test_R_PUB_08_flush_resolver_after_apply(
    sessions: sessionmaker[Session],
    clock: FakeClock,
    registry: FakeRegistry,
    policy: NamePolicy,
    flush_on_apply: bool,
) -> None:
    resolver = FakeResolverControl()
    settings = DEFAULTS.model_copy(update={"flush_on_apply": flush_on_apply})
    publisher = Publisher(registry, resolver, clock, lambda session: settings, "172.28.0.10")
    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.register("shop.com", "a", nameservers=NS_PAIR),
    )
    with sessions.begin() as session:
        publisher.apply_due(session)
        publisher.apply_due(session)  # nothing new: no second flush
    assert resolver.flushed == (["shop.com"] if flush_on_apply else [])


def test_R_PUB_08_flush_failure_does_not_undo_publish(
    sessions: sessionmaker[Session],
    clock: FakeClock,
    registry: FakeRegistry,
    policy: NamePolicy,
) -> None:
    resolver = FlakyResolver()
    publisher = Publisher(registry, resolver, clock, lambda session: DEFAULTS, "172.28.0.10")
    change(
        sessions,
        clock,
        publisher,
        policy,
        lambda d: d.register("shop.com", "a", nameservers=NS_PAIR),
    )
    with sessions.begin() as session:
        assert publisher.apply_due(session).applied == ["shop.com"]
    assert resolver.flushed == ["shop.com"]
    assert "shop.com" in registry.zone
