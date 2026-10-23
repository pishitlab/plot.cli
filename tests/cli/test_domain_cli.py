import json

from tests.cli.conftest import Plot

NS = ["--ns", "ns1.myhost.net", "--ns", "ns2.myhost.net"]


def test_check(plot: Plot) -> None:
    result = plot("domain", "check", "Shop.COM")
    assert (result.exit_code, result.output) == (0, "shop.com: available\n")
    plot("domain", "register", "shop.com")
    result = plot("domain", "check", "shop.com", "--json")
    assert json.loads(result.output) == {
        "name": "shop.com",
        "available": False,
        "reason": "DOMAIN_EXISTS",
    }
    assert "unavailable (DOMAIN_EXISTS)" in plot("domain", "check", "shop.com").output


def test_register_with_options_and_info(plot: Plot) -> None:
    result = plot(
        "domain", "register", "shop.com", "--years", "2", "--owner", "alice", *NS, "--json"
    )
    assert result.exit_code == 0, result.output
    body = json.loads(result.output)
    assert (body["owner"], body["nameservers"]) == ("alice", ["ns1.myhost.net", "ns2.myhost.net"])
    assert body["expires_at"] == "2028-01-01T00:00:00Z"
    text = plot("domain", "info", "shop.com").output
    assert "name:         shop.com" in text
    assert "nameservers:  ns1.myhost.net, ns2.myhost.net" in text
    assert "overrides:    delay=none ttl=none" in text


def test_register_defaults_owner(plot: Plot) -> None:
    body = json.loads(plot("domain", "register", "shop.com", "--json").output)
    assert body["owner"] == "cli"


def test_api_errors_exit_1_with_code_message(plot: Plot) -> None:
    plot("domain", "register", "shop.com")
    result = plot("domain", "register", "shop.com")
    assert result.exit_code == 1
    assert result.output == "DOMAIN_EXISTS: domain already registered\n"
    result = plot("domain", "info", "nope.com")
    assert (result.exit_code, result.output) == (1, "DOMAIN_NOT_FOUND: domain not found\n")


def test_usage_errors_exit_2(plot: Plot) -> None:
    assert plot("domain", "register").exit_code == 2  # missing name
    assert plot("domain", "renew", "shop.com").exit_code == 2  # missing --years
    assert plot("domain", "register", "shop.com", "--years", "x").exit_code == 2


def test_list_all_pages_with_filters(plot: Plot) -> None:
    for name, owner in [("b.com", "x"), ("a.com", "y"), ("c.net", "x")]:
        plot("domain", "register", name, "--owner", owner)
    body = json.loads(plot("domain", "list", "--json").output)
    assert [d["name"] for d in body["items"]] == ["a.com", "b.com", "c.net"]
    assert [
        d["name"]
        for d in json.loads(plot("domain", "list", "--owner", "x", "--json").output)["items"]
    ] == ["b.com", "c.net"]
    text = plot("domain", "list", "--prefix", "c").output
    assert text.startswith("c.net  x  expires ")
    assert plot("domain", "list", "--prefix", "zzz").output == "no domains\n"


def test_renew_delete(plot: Plot) -> None:
    plot("domain", "register", "shop.com")
    body = json.loads(plot("domain", "renew", "shop.com", "--years", "3", "--json").output)
    assert body["expires_at"] == "2030-01-01T00:00:00Z"
    result = plot("domain", "renew", "shop.com", "--years", "10")
    assert (result.exit_code, result.output.split(":")[0]) == (1, "RENEW_LIMIT")
    assert plot("domain", "delete", "shop.com").output == "deleted shop.com\n"
    plot("domain", "register", "shop.com")
    assert json.loads(plot("domain", "delete", "shop.com", "--json").output) == {
        "deleted": "shop.com"
    }
    result = plot("domain", "delete", "shop.com")
    assert result.exit_code == 1 and result.output.startswith("DOMAIN_NOT_FOUND")


def test_hold_release_and_expire_now(plot: Plot) -> None:
    plot("domain", "register", "shop.com", *NS)
    assert json.loads(plot("domain", "hold", "shop.com", "--json").output)["status"] == [
        "serverHold"
    ]
    assert "status:       -" in plot("domain", "release", "shop.com").output
    body = json.loads(plot("domain", "expire-now", "shop.com", "--json").output)
    assert body["expired"] is True
    assert "(expired)" in plot("domain", "info", "shop.com").output
