from fastapi.testclient import TestClient

from plot.cli.client import ApiClient


def test_hosts_list_create_update_delete(ui: TestClient, api: ApiClient) -> None:
    api.post("/domains", {"name": "shop.com", "owner": "a"})
    page = ui.post(
        "/ui/hosts", data={"name": "ns1.shop.com", "ipv4": "192.168.1.10 192.168.1.11", "ipv6": ""}
    ).text
    assert "created ns1.shop.com" in page
    assert 'value="192.168.1.10 192.168.1.11"' in page
    assert api.get("/hosts/ns1.shop.com")["ipv4"] == ["192.168.1.10", "192.168.1.11"]
    ui.post(
        "/ui/hosts/ns1.shop.com/addresses", data={"ipv4": "192.168.1.20", "ipv6": "2001:db8::1"}
    )
    host = api.get("/hosts/ns1.shop.com")
    assert (host["ipv4"], host["ipv6"]) == (["192.168.1.20"], ["2001:db8::1"])
    ui.post("/ui/hosts", data={"name": "ns1.other.net"})
    page = ui.get("/ui/hosts").text
    assert (
        '<span class="tag">external</span>' in page
        and '<span class="tag">subordinate</span>' in page
    )
    assert "deleted ns1.other.net" in ui.post("/ui/hosts/ns1.other.net/delete").text
    assert [h["name"] for h in api.get("/hosts")["items"]] == ["ns1.shop.com"]


def test_host_errors_are_flashed(ui: TestClient, api: ApiClient) -> None:
    api.post("/domains", {"name": "shop.com", "owner": "a"})
    assert "HOST_ADDR_REQUIRED" in ui.post("/ui/hosts", data={"name": "ns1.shop.com"}).text
    assert (
        "HOST_ADDR_FORBIDDEN"
        in ui.post("/ui/hosts", data={"name": "ns1.x.net", "ipv4": "192.168.1.1"}).text
    )
    api.post("/hosts", {"name": "ns1.shop.com", "ipv4": ["192.168.1.1"]})
    assert (
        "INVALID_ADDRESS"
        in ui.post("/ui/hosts/ns1.shop.com/addresses", data={"ipv4": "127.0.0.1"}).text
    )
    api.post(
        "/domains", {"name": "blog.com", "owner": "a", "nameservers": ["ns1.shop.com", "ns1.x.net"]}
    )
    assert "HOST_IN_USE" in ui.post("/ui/hosts/ns1.shop.com/delete").text
    assert "blog.com" in ui.get("/ui/hosts").text
