import pytest
from fastapi.testclient import TestClient

from plot.api.deps import AppState
from tests.api.helpers import error_code, register
from tests.fakes import FakeDnsPublisher


def test_create_subordinate_and_external(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/v1/hosts",
        json={"name": "NS1.shop.com.", "ipv4": ["192.168.1.10"], "ipv6": ["2001:db8::1"]},
    )
    assert response.status_code == 201
    assert response.json() == {
        "name": "ns1.shop.com",
        "kind": "subordinate",
        "parent_domain": "shop.com",
        "ipv4": ["192.168.1.10"],
        "ipv6": ["2001:db8::1"],
        "used_by": [],
    }
    external = client.post("/api/v1/hosts", json={"name": "ns1.other.net"}).json()
    assert (external["kind"], external["parent_domain"]) == ("external", None)


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"name": "localhost"}, 400, "INVALID_NAME"),
        ({"name": "ns1.shop.com"}, 400, "HOST_ADDR_REQUIRED"),
        ({"name": "ns1.other.net", "ipv4": ["192.168.1.1"]}, 400, "HOST_ADDR_FORBIDDEN"),
        ({"name": "ns1.shop.com", "ipv4": ["127.0.0.1"]}, 400, "INVALID_ADDRESS"),
        ({"name": "ns1.shop.com", "ipv4": "192.168.1.1"}, 400, "VALIDATION_ERROR"),
    ],
)
def test_create_errors(client: TestClient, body: dict[str, object], status: int, code: str) -> None:
    register(client)
    response = client.post("/api/v1/hosts", json=body)
    assert (response.status_code, error_code(response)) == (status, code)


def test_create_duplicate(client: TestClient) -> None:
    client.post("/api/v1/hosts", json={"name": "ns1.other.net"})
    response = client.post("/api/v1/hosts", json={"name": "NS1.other.net"})
    assert (response.status_code, error_code(response)) == (409, "HOST_EXISTS")


def test_get_and_list(client: TestClient) -> None:
    client.post("/api/v1/hosts", json={"name": "ns2.other.net"})
    client.post("/api/v1/hosts", json={"name": "ns1.other.net"})
    assert client.get("/api/v1/hosts/ns1.other.net").json()["name"] == "ns1.other.net"
    assert [h["name"] for h in client.get("/api/v1/hosts").json()["items"]] == [
        "ns1.other.net",
        "ns2.other.net",
    ]
    response = client.get("/api/v1/hosts/ns9.other.net")
    assert (response.status_code, error_code(response)) == (404, "HOST_NOT_FOUND")


def test_update_addresses(client: TestClient, state: AppState) -> None:
    register(client)
    client.post("/api/v1/hosts", json={"name": "ns1.shop.com", "ipv4": ["192.168.1.10"]})
    assert isinstance(state.publisher, FakeDnsPublisher)
    state.publisher.reset()
    body = client.put("/api/v1/hosts/ns1.shop.com", json={"ipv4": ["192.168.1.20"]}).json()
    assert body["ipv4"] == ["192.168.1.20"]
    assert state.publisher.changed == {"shop.com"}
    response = client.put("/api/v1/hosts/ns1.shop.com", json={"ipv4": []})
    assert (response.status_code, error_code(response)) == (400, "HOST_ADDR_REQUIRED")
    response = client.put("/api/v1/hosts/ns9.shop.com", json={"ipv4": ["192.168.1.1"]})
    assert (response.status_code, error_code(response)) == (404, "HOST_NOT_FOUND")


def test_delete(client: TestClient) -> None:
    client.post("/api/v1/hosts", json={"name": "ns1.other.net"})
    assert client.delete("/api/v1/hosts/ns1.other.net").status_code == 204
    response = client.delete("/api/v1/hosts/ns1.other.net")
    assert (response.status_code, error_code(response)) == (404, "HOST_NOT_FOUND")
