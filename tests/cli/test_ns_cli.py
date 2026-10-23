import json

from tests.cli.conftest import Plot


def test_set_and_clear(plot: Plot) -> None:
    plot("domain", "register", "shop.com")
    result = plot("ns", "set", "shop.com", "ns1.myhost.net", "ns2.myhost.net", "--json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["nameservers"] == ["ns1.myhost.net", "ns2.myhost.net"]
    assert (
        "nameservers:  ns1.myhost.net, ns2.myhost.net" in plot("domain", "info", "shop.com").output
    )
    assert "nameservers:  -" in plot("ns", "clear", "shop.com").output
    assert json.loads(plot("ns", "clear", "shop.com", "--json").output)["nameservers"] == []


def test_errors(plot: Plot) -> None:
    plot("domain", "register", "shop.com")
    result = plot("ns", "set", "shop.com", "ns1.myhost.net")
    assert result.exit_code == 1 and result.output.startswith("INVALID_NS_COUNT: ")
    result = plot("ns", "set", "nope.com", "ns1.a.net", "ns2.a.net")
    assert result.exit_code == 1 and result.output.startswith("DOMAIN_NOT_FOUND: ")
    assert plot("ns", "set", "shop.com").exit_code == 2
    assert plot("ns", "clear").exit_code == 2
