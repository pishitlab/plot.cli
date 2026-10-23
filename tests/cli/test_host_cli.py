import json

from tests.cli.conftest import Plot


def test_create_info_list_update_delete(plot: Plot) -> None:
    plot("domain", "register", "shop.com")
    result = plot(
        "host",
        "create",
        "ns1.shop.com",
        "--ipv4",
        "192.168.1.10",
        "--ipv4",
        "192.168.1.11",
        "--ipv6",
        "2001:db8::1",
        "--json",
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "name": "ns1.shop.com",
        "kind": "subordinate",
        "parent_domain": "shop.com",
        "ipv4": ["192.168.1.10", "192.168.1.11"],
        "ipv6": ["2001:db8::1"],
        "used_by": [],
    }
    assert plot("host", "info", "ns1.shop.com").output == (
        "ns1.shop.com  subordinate of shop.com  addresses: 192.168.1.10, 192.168.1.11,"
        " 2001:db8::1  used by: -\n"
    )
    plot("host", "create", "ns1.other.net")
    assert plot("host", "list").output.splitlines() == [
        "ns1.other.net  external  addresses: -  used by: -",
        "ns1.shop.com  subordinate of shop.com  addresses: 192.168.1.10, 192.168.1.11,"
        " 2001:db8::1  used by: -",
    ]
    assert [h["name"] for h in json.loads(plot("host", "list", "--json").output)["items"]] == [
        "ns1.other.net",
        "ns1.shop.com",
    ]
    updated = json.loads(
        plot("host", "update", "ns1.shop.com", "--ipv4", "192.168.1.20", "--json").output
    )
    assert (updated["ipv4"], updated["ipv6"]) == (["192.168.1.20"], ["2001:db8::1"])
    assert plot("host", "delete", "ns1.other.net").output == "deleted ns1.other.net\n"
    assert json.loads(plot("host", "delete", "ns1.shop.com", "--json").output) == {
        "deleted": "ns1.shop.com"
    }
    assert plot("host", "list").output == "no hosts\n"


def test_errors(plot: Plot) -> None:
    plot("domain", "register", "shop.com")
    for args, code in [
        (["host", "create", "ns1.shop.com"], "HOST_ADDR_REQUIRED"),
        (["host", "create", "ns1.other.net", "--ipv4", "192.168.1.1"], "HOST_ADDR_FORBIDDEN"),
        (["host", "create", "ns1.shop.com", "--ipv4", "127.0.0.1"], "INVALID_ADDRESS"),
        (["host", "info", "ns9.shop.com"], "HOST_NOT_FOUND"),
        (["host", "update", "ns9.shop.com", "--ipv4", "192.168.1.1"], "HOST_NOT_FOUND"),
        (["host", "delete", "ns9.shop.com"], "HOST_NOT_FOUND"),
    ]:
        result = plot(*args)
        assert result.exit_code == 1, args
        assert result.output.startswith(f"{code}: "), result.output
    plot("host", "create", "ns1.shop.com", "--ipv4", "192.168.1.10")
    plot("domain", "register", "blog.com", "--ns", "ns1.shop.com", "--ns", "ns1.x.net")
    result = plot("host", "delete", "ns1.shop.com")
    assert result.exit_code == 1 and result.output.startswith("HOST_IN_USE: ")
    assert plot("host", "create").exit_code == 2
