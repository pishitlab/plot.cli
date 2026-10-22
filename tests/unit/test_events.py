from datetime import timedelta

from plot.core.clock import FakeClock
from plot.services.context import ServiceContext
from plot.services.events import domain_history
from tests.conftest import T0


def test_R_DOM_07_record_writes_event_with_request_context(ctx: ServiceContext) -> None:
    event = ctx.record(
        "domain.register",
        domain_name="shop.com",
        before=None,
        after={"name": "shop.com", "owner": "alice"},
    )
    ctx.session.flush()
    assert event.id is not None
    assert (event.ts, event.actor, event.request_id, event.action) == (
        T0,
        "test",
        "req-1",
        "domain.register",
    )
    assert event.after == {"name": "shop.com", "owner": "alice"}


def test_domain_history_includes_subordinate_hosts_in_order(
    ctx: ServiceContext, clock: FakeClock
) -> None:
    ctx.record("domain.register", domain_name="shop.com")
    clock.advance(timedelta(seconds=1))
    ctx.record("host.create", host_name="ns1.shop.com")
    ctx.record("domain.register", domain_name="myshop.com")
    ctx.record("host.create", host_name="ns1.myshop.com")
    ctx.record("domain.nameservers", domain_name="shop.com")
    ctx.session.flush()
    history = domain_history(ctx.session, "shop.com")
    assert [(e.action, e.domain_name or e.host_name) for e in history] == [
        ("domain.register", "shop.com"),
        ("host.create", "ns1.shop.com"),
        ("domain.nameservers", "shop.com"),
    ]
