from sqlalchemy.orm import Session

from plot.core.clock import FakeClock, SystemClock
from plot.services.ports import Clock, DnsPublisher, ResolverControl
from tests.fakes import FakeDnsPublisher, FakeResolverControl


def test_fakes_satisfy_ports() -> None:
    publisher: DnsPublisher = FakeDnsPublisher()
    resolver: ResolverControl = FakeResolverControl()
    clocks: list[Clock] = [FakeClock(), SystemClock()]
    assert publisher and resolver and clocks


def test_fake_publisher_records_changes() -> None:
    publisher = FakeDnsPublisher()
    session = Session()
    publisher.domains_changed(session, ["a.com"])
    publisher.domains_changed(session, {"b.com", "a.com"})
    assert publisher.calls == [frozenset({"a.com"}), frozenset({"a.com", "b.com"})]
    assert publisher.changed == {"a.com", "b.com"}
    publisher.reset()
    assert publisher.changed == set()


def test_fake_resolver_records_flushes() -> None:
    resolver = FakeResolverControl()
    resolver.flush("a.com")
    resolver.flush()
    assert resolver.flushed == ["a.com", None]
