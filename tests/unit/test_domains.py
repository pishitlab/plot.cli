from datetime import UTC, datetime, timedelta

import pytest

from plot.core.clock import FakeClock
from plot.core.errors import (
    DomainExists,
    DomainNotFound,
    HostInUse,
    InvalidName,
    InvalidPeriod,
    InvalidStatus,
    NotRegistrable,
    RenewLimit,
    ReservedName,
    TldNotSupported,
    ValidationFailed,
)
from plot.db.models import Domain, Event, Host
from plot.services.context import ServiceContext
from plot.services.domains import DomainService, Overrides
from plot.services.hosts import HostService, find_host
from tests.conftest import T0
from tests.fakes import FakeDnsPublisher
from tests.helpers import actions, use_as_ns


@pytest.fixture
def domains(ctx: ServiceContext) -> DomainService:
    return DomainService(ctx)


@pytest.fixture
def hosts(ctx: ServiceContext) -> HostService:
    return HostService(ctx)


def _host(ctx: ServiceContext, name: str) -> Host:
    host = find_host(ctx.session, name)
    assert host is not None
    return host


def _domain(ctx: ServiceContext, name: str) -> Domain:
    return DomainService(ctx).load(name)


# --- register / check -------------------------------------------------------


def test_register_normalizes_and_stores_parts(
    domains: DomainService, ctx: ServiceContext, publisher: FakeDnsPublisher
) -> None:
    view = domains.register(" Shop.CO.TH. ", owner="alice")
    assert view.name == "shop.co.th"
    assert view.owner == "alice"
    assert view.status == [] and view.nameservers == [] and not view.expired
    assert view.overrides == Overrides(None, None)
    row = _domain(ctx, "shop.co.th")
    assert (row.label, row.suffix) == ("shop", "co.th")
    assert len(row.auth_code) >= 16
    assert publisher.changed == {"shop.co.th"}


@pytest.mark.parametrize(
    ("raw", "error"),
    [
        ("bad_name.com", InvalidName),
        ("www.shop.com", NotRegistrable),
        ("shop.xyz", TldNotSupported),
        ("github.com", ReservedName),
    ],
)
def test_register_applies_name_rules(
    domains: DomainService, raw: str, error: type[Exception]
) -> None:
    with pytest.raises(error):
        domains.register(raw, owner="alice")


@pytest.mark.parametrize("owner", ["", "   ", "x" * 256])
def test_register_requires_owner(domains: DomainService, owner: str) -> None:
    with pytest.raises(ValidationFailed):
        domains.register("shop.com", owner=owner)


def test_R_DOM_01_duplicate_name_rejected_for_any_owner(domains: DomainService) -> None:
    domains.register("shop.com", owner="alice")
    with pytest.raises(DomainExists):
        domains.register("SHOP.com.", owner="bob")


def test_check_reports_availability_and_reason(domains: DomainService) -> None:
    domains.register("shop.com", owner="alice")
    assert domains.check("free.com").available
    taken = domains.check("Shop.COM")
    assert (taken.name, taken.available, taken.reason) == ("shop.com", False, "DOMAIN_EXISTS")
    assert domains.check("github.com").reason == "RESERVED_NAME"
    assert domains.check("www.free.com").reason == "NOT_REGISTRABLE"
    assert domains.check(" bad_name.com ").reason == "INVALID_NAME"
    assert domains.check("free.xyz").reason == "TLD_NOT_SUPPORTED"


def test_R_DOM_02_default_period_and_calendar_expiry(
    domains: DomainService, clock: FakeClock
) -> None:
    clock.set(datetime(2028, 2, 29, 10, 0, tzinfo=UTC))
    view = domains.register("shop.com", owner="alice")
    assert view.created_at == datetime(2028, 2, 29, 10, 0, tzinfo=UTC)
    assert view.expires_at == datetime(2029, 2, 28, 10, 0, tzinfo=UTC)
    assert domains.register("blog.com", owner="a", years=10).expires_at == datetime(
        2038, 2, 28, 10, 0, tzinfo=UTC
    )


def test_R_DOM_02_default_years_from_settings(ctx: ServiceContext) -> None:
    ctx.settings = ctx.settings.model_copy(update={"default_years": 3})
    view = DomainService(ctx).register("shop.com", owner="alice")
    assert view.expires_at == T0.replace(year=2029)


@pytest.mark.parametrize("years", [0, 11, -1])
def test_R_DOM_02_years_must_be_1_to_10(domains: DomainService, years: int) -> None:
    with pytest.raises(InvalidPeriod):
        domains.register("shop.com", owner="alice", years=years)


# --- renew --------------------------------------------------------------------


def test_R_DOM_03_renew_extends_from_current_expiry(
    domains: DomainService, clock: FakeClock
) -> None:
    domains.register("shop.com", owner="alice", years=2)
    clock.advance(timedelta(days=100))
    assert domains.renew("shop.com", 3).expires_at == T0.replace(year=2031)


def test_R_DOM_03_renew_cannot_exceed_ten_years_remaining(
    domains: DomainService, clock: FakeClock
) -> None:
    domains.register("shop.com", owner="alice", years=9)
    domains.renew("shop.com", 1)  # exactly 10 years from now
    with pytest.raises(RenewLimit):
        domains.renew("shop.com", 1)
    clock.advance(timedelta(days=366))
    assert domains.renew("shop.com", 1).expires_at == T0.replace(year=2037)


@pytest.mark.parametrize("years", [0, 11])
def test_R_DOM_03_renew_period_validated(domains: DomainService, years: int) -> None:
    domains.register("shop.com", owner="alice")
    with pytest.raises(InvalidPeriod):
        domains.renew("shop.com", years)


def test_renew_unknown_domain(domains: DomainService) -> None:
    with pytest.raises(DomainNotFound):
        domains.renew("nope.com", 1)


# --- delete -------------------------------------------------------------------


def test_R_DOM_04_delete_frees_name_and_removes_subordinate_hosts(
    domains: DomainService, hosts: HostService, ctx: ServiceContext, publisher: FakeDnsPublisher
) -> None:
    domains.register("shop.com", owner="alice")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    hosts.create("ns2.shop.com", ipv4=["192.168.1.11"])
    use_as_ns(ctx.session, _domain(ctx, "shop.com"), _host(ctx, "ns1.shop.com"))
    publisher.reset()
    domains.delete("shop.com")
    assert ctx.session.query(Host).count() == 0
    assert publisher.changed == {"shop.com"}
    with pytest.raises(DomainNotFound):
        domains.get("shop.com")
    assert domains.register("shop.com", owner="bob").owner == "bob"


def test_R_DOM_04_delete_blocked_when_subordinate_host_used_elsewhere(
    domains: DomainService, hosts: HostService, ctx: ServiceContext
) -> None:
    domains.register("shop.com", owner="alice")
    domains.register("blog.com", owner="alice")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    use_as_ns(ctx.session, _domain(ctx, "blog.com"), _host(ctx, "ns1.shop.com"))
    with pytest.raises(HostInUse):
        domains.delete("shop.com")
    assert domains.get("shop.com").name == "shop.com"


def test_R_DOM_04_delete_republishes_glue_owner_and_drops_unused_external(
    domains: DomainService, hosts: HostService, ctx: ServiceContext, publisher: FakeDnsPublisher
) -> None:
    domains.register("shop.com", owner="alice")
    domains.register("blog.com", owner="alice")
    hosts.create("ns1.shop.com", ipv4=["192.168.1.10"])
    hosts.create("ns1.other.net")
    use_as_ns(
        ctx.session,
        _domain(ctx, "blog.com"),
        _host(ctx, "ns1.shop.com"),
        _host(ctx, "ns1.other.net"),
    )
    publisher.reset()
    domains.delete("blog.com")
    # shop.com's glue was published only because blog.com used ns1.shop.com (R-PUB-03)
    assert publisher.changed == {"blog.com", "shop.com"}
    assert find_host(ctx.session, "ns1.other.net") is None
    assert find_host(ctx.session, "ns1.shop.com") is not None


# --- status -------------------------------------------------------------------


def test_R_DOM_05_settable_statuses(domains: DomainService, publisher: FakeDnsPublisher) -> None:
    domains.register("shop.com", owner="alice")
    view = domains.update_status("shop.com", add=["serverHold", "clientHold"])
    assert view.status == ["clientHold", "serverHold"]
    view = domains.update_status(
        "shop.com", add=["pendingDelete", "clientHold"], remove=["serverHold"]
    )
    assert view.status == ["clientHold", "pendingDelete"]
    view = domains.update_status("shop.com", remove=["clientHold", "serverHold"])
    assert view.status == ["pendingDelete"]
    assert publisher.calls[-1] == frozenset({"shop.com"})


@pytest.mark.parametrize(
    ("add", "remove"),
    [(["ok"], []), (["clienthold"], []), ([], ["expired"]), (["clientHold"], ["clientHold"])],
)
def test_R_DOM_05_rejects_other_statuses(
    domains: DomainService, add: list[str], remove: list[str]
) -> None:
    domains.register("shop.com", owner="alice")
    with pytest.raises(InvalidStatus):
        domains.update_status("shop.com", add=add, remove=remove)


# --- overrides, get, list -------------------------------------------------------


def test_overrides_set_keep_and_clear(domains: DomainService) -> None:
    domains.register("shop.com", owner="alice")
    assert domains.set_overrides("shop.com", propagation_delay=20).overrides == Overrides(20, None)
    assert domains.set_overrides("shop.com", ns_ttl=60).overrides == Overrides(20, 60)
    assert domains.set_overrides("shop.com", propagation_delay=None).overrides == Overrides(
        None, 60
    )


@pytest.mark.parametrize(("delay", "ttl"), [(-1, None), (None, -5), (None, 2**31)])
def test_overrides_validated(domains: DomainService, delay: int | None, ttl: int | None) -> None:
    domains.register("shop.com", owner="alice")
    with pytest.raises(ValidationFailed):
        domains.set_overrides("shop.com", propagation_delay=delay, ns_ttl=ttl)


def test_list_filters_and_paginates(domains: DomainService) -> None:
    for name, owner in [("b.com", "x"), ("a.com", "x"), ("c.net", "y"), ("ab.com", "y")]:
        domains.register(name, owner=owner)
    page = domains.list_domains(limit=2)
    assert [d.name for d in page.items] == ["a.com", "ab.com"]
    assert page.next_cursor == "ab.com"
    page = domains.list_domains(limit=2, cursor=page.next_cursor)
    assert [d.name for d in page.items] == ["b.com", "c.net"]
    assert page.next_cursor is None
    assert [d.name for d in domains.list_domains(prefix="A").items] == ["a.com", "ab.com"]
    assert [d.name for d in domains.list_domains(owner="y").items] == ["ab.com", "c.net"]
    assert domains.list_domains(prefix="%").items == []


@pytest.mark.parametrize("limit", [0, 201])
def test_list_limit_bounds(domains: DomainService, limit: int) -> None:
    with pytest.raises(ValidationFailed):
        domains.list_domains(limit=limit)


def test_get_unknown_and_invalid(domains: DomainService) -> None:
    with pytest.raises(DomainNotFound):
        domains.get("nope.com")
    with pytest.raises(InvalidName):
        domains.get("bad_name.com")


def test_R_DOM_07_domain_changes_write_events(domains: DomainService, ctx: ServiceContext) -> None:
    domains.register("shop.com", owner="alice")
    domains.renew("shop.com", 1)
    domains.update_status("shop.com", add=["clientHold"])
    domains.set_overrides("shop.com", ns_ttl=60)
    domains.delete("shop.com")
    assert actions(ctx.session) == [
        "domain.register",
        "domain.renew",
        "domain.status",
        "domain.overrides",
        "domain.delete",
    ]
    renew = ctx.session.query(Event).filter_by(action="domain.renew").one()
    assert renew.before is not None and renew.after is not None
    assert renew.before["expires_at"] == "2027-01-01T00:00:00+00:00"
    assert renew.after["expires_at"] == "2028-01-01T00:00:00+00:00"
    assert (renew.actor, renew.request_id) == ("test", "req-1")
