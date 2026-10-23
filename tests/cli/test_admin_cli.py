import json

from plot.api.deps import AppState
from tests.cli.conftest import Plot
from tests.fakes import FakeResolverControl


def test_override_values_none_and_errors(plot: Plot) -> None:
    plot("domain", "register", "shop.com")
    body = json.loads(plot("override", "shop.com", "--delay", "20", "--ttl", "60", "--json").output)
    assert body["overrides"] == {"propagation_delay": 20, "ns_ttl": 60}
    assert (
        "overrides:    delay=none ttl=60" in plot("override", "shop.com", "--delay", "none").output
    )
    body = json.loads(plot("override", "shop.com", "--ttl", "NONE", "--json").output)
    assert body["overrides"] == {"propagation_delay": None, "ns_ttl": None}
    assert plot("override", "shop.com", "--delay", "soon").exit_code == 2
    assert plot("override", "shop.com", "--delay", "-5").exit_code == 2
    result = plot("override", "nope.com", "--delay", "1")
    assert result.exit_code == 1 and result.output.startswith("DOMAIN_NOT_FOUND: ")


def test_settings_show_and_change(plot: Plot) -> None:
    assert plot("admin", "settings").output.splitlines() == [
        "default_years: 1",
        "expiry_grace_days: 30",
        "flush_on_apply: True",
        "ns_ttl: 300",
        "propagation_delay: 0",
    ]
    body = json.loads(plot("admin", "settings", "--delay", "20", "--ttl", "60", "--json").output)
    assert (body["propagation_delay"], body["ns_ttl"]) == (20, 60)
    assert json.loads(plot("admin", "settings", "--json").output)["propagation_delay"] == 20
    assert plot("admin", "settings", "--delay", "-1").exit_code == 2


def test_reset(plot: Plot) -> None:
    plot("domain", "register", "scn-a.com")
    plot("domain", "register", "keep.com")
    assert plot("admin", "reset", "--prefix", "scn-").output == "removed 1 domains, 0 hosts\n"
    body = json.loads(plot("admin", "reset", "--all", "--json").output)
    assert body == {"deleted_domains": ["keep.com"], "deleted_hosts": []}
    assert plot("admin", "reset").exit_code == 2
    assert plot("admin", "reset", "--prefix", "a", "--all").exit_code == 2
    result = plot("admin", "reset", "--prefix", " ")
    assert result.exit_code == 1 and result.output.startswith("VALIDATION_ERROR: ")


def test_flush(plot: Plot, state: AppState) -> None:
    assert plot("admin", "flush", "Shop.COM").output == "flushed shop.com\n"
    assert json.loads(plot("admin", "flush", "--json").output) == {"flushed": None}
    assert plot("admin", "flush").output == "flushed everything\n"
    assert isinstance(state.resolver, FakeResolverControl)
    assert state.resolver.flushed == ["shop.com", None, None]
