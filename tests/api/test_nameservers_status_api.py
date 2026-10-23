import pytest
from fastapi.testclient import TestClient

from plot.api.deps import AppState
from tests.api.helpers import NS_PAIR, error_code, register
from tests.fakes import FakeDnsPublisher


def test_set_nameservers_and_clear(client: TestClient, state: AppState) -> None:
    register(client)
    response = client.put("/api/v1/domains/shop.com/nameservers", json={"nameservers": NS_PAIR})
    assert response.status_code == 200
    assert response.json()["nameservers"] == NS_PAIR
    assert [h["name"] for h in client.get("/api/v1/hosts").json()["items"]] == NS_PAIR
    cleared = client.put("/api/v1/domains/shop.com/nameservers", json={"nameservers": []})
    assert cleared.json()["nameservers"] == []
    assert client.get("/api/v1/hosts").json()["items"] == []
    assert isinstance(state.publisher, FakeDnsPublisher)
    assert state.publisher.calls[-1] == frozenset({"shop.com"})


@pytest.mark.parametrize(
    ("names", "status", "code"),
    [
        (["ns1.x.net"], 400, "INVALID_NS_COUNT"),
        (["ns1.x.net", "NS1.X.NET"], 400, "DUPLICATE_NS"),
        (["ns1.x.net", "bad_ns.x.net"], 400, "INVALID_NAME"),
        (["ns1.shop.com", "ns1.x.net"], 404, "HOST_NOT_FOUND"),
    ],
)
def test_set_nameservers_errors(
    client: TestClient, names: list[str], status: int, code: str
) -> None:
    register(client)
    response = client.put("/api/v1/domains/shop.com/nameservers", json={"nameservers": names})
    assert (response.status_code, error_code(response)) == (status, code)


def test_glue_required(client: TestClient) -> None:
    client.post("/api/v1/hosts", json={"name": "ns1.shop.com"})  # external before shop.com exists
    register(client)
    response = client.put(
        "/api/v1/domains/shop.com/nameservers", json={"nameservers": ["ns1.shop.com", "ns1.x.net"]}
    )
    assert (response.status_code, error_code(response)) == (400, "GLUE_REQUIRED")


def test_set_nameservers_unknown_domain(client: TestClient) -> None:
    response = client.put("/api/v1/domains/nope.com/nameservers", json={"nameservers": NS_PAIR})
    assert (response.status_code, error_code(response)) == (404, "DOMAIN_NOT_FOUND")


def test_host_in_use_blocks_host_and_domain_delete(client: TestClient) -> None:
    register(client)
    register(client, "blog.com")
    client.post("/api/v1/hosts", json={"name": "ns1.shop.com", "ipv4": ["192.168.1.10"]})
    response = client.put(
        "/api/v1/domains/blog.com/nameservers", json={"nameservers": ["ns1.shop.com", "ns1.x.net"]}
    )
    assert response.status_code == 200
    assert client.get("/api/v1/hosts/ns1.shop.com").json()["used_by"] == ["blog.com"]
    for path in ("/api/v1/hosts/ns1.shop.com", "/api/v1/domains/shop.com"):
        response = client.delete(path)
        assert (response.status_code, error_code(response)) == (409, "HOST_IN_USE")


def test_status_add_and_remove(client: TestClient) -> None:
    register(client)
    body = client.put("/api/v1/domains/shop.com/status", json={"add": ["serverHold"]}).json()
    assert body["status"] == ["serverHold"]
    body = client.put("/api/v1/domains/shop.com/status", json={"remove": ["serverHold"]}).json()
    assert body["status"] == []


@pytest.mark.parametrize(
    ("body", "code"),
    [({"add": ["ok"]}, "INVALID_STATUS"), ({"add": "serverHold"}, "VALIDATION_ERROR")],
)
def test_status_errors(client: TestClient, body: dict[str, object], code: str) -> None:
    register(client)
    response = client.put("/api/v1/domains/shop.com/status", json=body)
    assert (response.status_code, error_code(response)) == (400, code)


def test_overrides_absent_null_and_values(client: TestClient) -> None:
    register(client)
    url = "/api/v1/domains/shop.com/overrides"
    assert client.put(url, json={"propagation_delay": 20}).json()["overrides"] == {
        "propagation_delay": 20,
        "ns_ttl": None,
    }
    assert client.put(url, json={"ns_ttl": 60}).json()["overrides"] == {
        "propagation_delay": 20,
        "ns_ttl": 60,
    }
    assert client.put(url, json={"propagation_delay": None}).json()["overrides"] == {
        "propagation_delay": None,
        "ns_ttl": 60,
    }
    assert client.put(url, json={}).json()["overrides"]["ns_ttl"] == 60


@pytest.mark.parametrize("body", [{"ns_ttl": -1}, {"propagation_delay": "5"}, {"ttl": 5}])
def test_overrides_errors(client: TestClient, body: dict[str, object]) -> None:
    register(client)
    response = client.put("/api/v1/domains/shop.com/overrides", json=body)
    assert (response.status_code, error_code(response)) == (400, "VALIDATION_ERROR")
