import json
from typing import Any

import httpx
import pytest

from plot.dns.pdns_client import PdnsClient, PdnsError, root_rrsets, rrset_changes

NEW = {
    "nameservers": ["ns1.shop.com", "ns1.myhost.net"],
    "ttl": 300,
    "glue": {"ns1.shop.com": {"A": ["192.168.1.10"], "AAAA": []}},
}


def test_rrset_changes_replace_ns_and_glue() -> None:
    assert rrset_changes("shop.com", None, NEW) == [
        {
            "name": "shop.com.",
            "type": "NS",
            "ttl": 300,
            "changetype": "REPLACE",
            "records": [
                {"content": "ns1.shop.com.", "disabled": False},
                {"content": "ns1.myhost.net.", "disabled": False},
            ],
        },
        {
            "name": "ns1.shop.com.",
            "type": "A",
            "ttl": 300,
            "changetype": "REPLACE",
            "records": [{"content": "192.168.1.10", "disabled": False}],
        },
        {"name": "ns1.shop.com.", "type": "AAAA", "changetype": "DELETE"},
    ]


def test_rrset_changes_removal_deletes_everything_old() -> None:
    assert rrset_changes("shop.com", NEW, None) == [
        {"name": "shop.com.", "type": "NS", "changetype": "DELETE"},
        {"name": "ns1.shop.com.", "type": "A", "changetype": "DELETE"},
        {"name": "ns1.shop.com.", "type": "AAAA", "changetype": "DELETE"},
    ]


def test_rrset_changes_dropped_glue_host_is_deleted() -> None:
    new = {**NEW, "glue": {}}
    ops = rrset_changes("shop.com", NEW, new)
    assert {"name": "ns1.shop.com.", "type": "A", "changetype": "DELETE"} in ops


ROOT_NS_RRSET = {
    "name": ".",
    "type": "NS",
    "ttl": 3600,
    "records": [{"content": "a.root-servers.net.", "disabled": False}],
}


class FakePdns:
    def __init__(self, zone_exists: bool = True, fail: int | None = None) -> None:
        self.zone_exists = zone_exists
        self.fail = fail
        self.requests: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        assert request.headers["X-API-Key"] == "k"
        if self.fail:
            return httpx.Response(self.fail, json={"error": "boom"})
        if request.method == "GET" and request.url.path.endswith("/zones/=2E"):
            if not self.zone_exists:
                return httpx.Response(404, json={"error": "Not Found"})
            return httpx.Response(200, json={"rrsets": [ROOT_NS_RRSET]})
        if request.method == "GET":
            return httpx.Response(200, json={"id": "localhost"})
        return httpx.Response(201 if request.method == "POST" else 204)


def client(fake: FakePdns) -> PdnsClient:
    return PdnsClient("http://pdns:8081/", "k", transport=httpx.MockTransport(fake))


def test_ensure_root_zone_creates_when_missing() -> None:
    fake = FakePdns(zone_exists=False)
    client(fake).ensure_root_zone("172.28.0.10")
    method, path, body = fake.requests[-1]
    assert (method, path) == ("POST", "/api/v1/servers/localhost/zones")
    assert body["name"] == "." and body["soa_edit_api"] == "INCREASE"
    rrsets = {(r["name"], r["type"]): r for r in body["rrsets"]}
    assert rrsets[("a.root-servers.net.", "A")]["records"][0]["content"] == "172.28.0.10"
    assert rrsets[(".", "SOA")]["records"][0]["content"].endswith(" 5")
    assert all("changetype" not in r for r in body["rrsets"])


def test_ensure_root_zone_rewrites_existing() -> None:
    fake = FakePdns()
    client(fake).ensure_root_zone("172.28.0.10")
    assert [(m, p) for m, p, _ in fake.requests] == [
        ("GET", "/api/v1/servers/localhost/zones/=2E"),
        ("PUT", "/api/v1/servers/localhost/zones/=2E"),
        ("PATCH", "/api/v1/servers/localhost/zones/=2E"),
    ]
    patched = {(r["name"], r["type"]) for r in fake.requests[-1][2]["rrsets"]}
    assert patched == {(".", "SOA"), ("a.root-servers.net.", "A")}  # NS . already right


def test_ensure_root_zone_keeps_serial_and_skips_when_in_sync() -> None:
    in_sync = [
        {k: v for k, v in r.items() if k != "changetype"} for r in root_rrsets("172.28.0.10")
    ]
    soa = in_sync[0]["records"][0]["content"].replace(" 1 1800", " 42 1800")
    in_sync[0] = {**in_sync[0], "records": [{"content": soa}]}
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(200, json={"soa_edit_api": "INCREASE", "rrsets": in_sync})

    PdnsClient("http://pdns", "k", transport=httpx.MockTransport(handler)).ensure_root_zone(
        "172.28.0.10"
    )
    assert methods == ["GET"]


def test_ensure_root_zone_fixes_drift_keeping_serial() -> None:
    drifted = [
        {k: v for k, v in r.items() if k != "changetype"} for r in root_rrsets("172.28.0.99")
    ]
    drifted[0] = {**drifted[0], "records": [{"content": "a.root-servers.net. x. 42 1 1 1 3600"}]}
    patches: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"soa_edit_api": "INCREASE", "rrsets": drifted})
        patches.append(json.loads(request.content)["rrsets"])
        return httpx.Response(204)

    PdnsClient("http://pdns", "k", transport=httpx.MockTransport(handler)).ensure_root_zone(
        "172.28.0.10"
    )
    ops = {(r["name"], r["type"]): r for r in patches[0]}
    assert set(ops) == {(".", "SOA"), ("a.root-servers.net.", "A")}
    assert ops[(".", "SOA")]["records"][0]["content"] == (
        "a.root-servers.net. hostmaster.sandbox.invalid. 42 1800 900 604800 5"
    )


def test_apply_patches_root_zone() -> None:
    fake = FakePdns()
    client(fake).apply("shop.com", None, NEW)
    method, path, body = fake.requests[-1]
    assert (method, path) == ("PATCH", "/api/v1/servers/localhost/zones/=2E")
    assert body == {"rrsets": rrset_changes("shop.com", None, NEW)}


def test_zone_rrsets_and_ping() -> None:
    fake = FakePdns()
    c = client(fake)
    assert c.zone_rrsets() == [ROOT_NS_RRSET]
    assert c.ping()
    assert not client(FakePdns(fail=500)).ping()


def test_http_errors_raise_pdns_error() -> None:
    with pytest.raises(PdnsError, match="422"):
        client(FakePdns(fail=422)).apply("shop.com", None, NEW)

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    down = PdnsClient("http://pdns:8081", "k", transport=httpx.MockTransport(unreachable))
    with pytest.raises(PdnsError, match="unreachable"):
        down.apply("shop.com", None, NEW)
    assert not down.ping()
    down.close()
