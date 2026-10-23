from fastapi.testclient import TestClient

from tests.api.helpers import NS_PAIR, error_code, register


def test_history_lists_changes_with_request_ids(client: TestClient) -> None:
    created = client.post(
        "/api/v1/domains",
        json={"name": "shop.com", "owner": "alice"},
        headers={"X-Request-ID": "req-create"},
    )
    assert created.status_code == 201
    client.post("/api/v1/hosts", json={"name": "ns1.shop.com", "ipv4": ["192.168.1.10"]})
    client.put("/api/v1/domains/shop.com/nameservers", json={"nameservers": NS_PAIR})
    items = client.get("/api/v1/domains/SHOP.com/history").json()["items"]
    # external hosts ns*.myhost.net are not part of shop.com's history
    assert [i["action"] for i in items] == ["domain.register", "host.create", "domain.nameservers"]
    first = items[0]
    assert first["request_id"] == "req-create"
    assert first["actor"] == "api"
    assert first["ts"] == "2026-01-01T00:00:00Z"
    assert first["before"] is None and first["after"]["name"] == "shop.com"
    assert items[-1]["after"]["nameservers"] == NS_PAIR


def test_history_kept_after_delete(client: TestClient) -> None:
    register(client)
    client.delete("/api/v1/domains/shop.com")
    actions = [i["action"] for i in client.get("/api/v1/domains/shop.com/history").json()["items"]]
    assert actions == ["domain.register", "domain.delete"]


def test_history_unknown_domain(client: TestClient) -> None:
    response = client.get("/api/v1/domains/nope.com/history")
    assert (response.status_code, error_code(response)) == (404, "DOMAIN_NOT_FOUND")
    response = client.get("/api/v1/domains/bad_name.com/history")
    assert (response.status_code, error_code(response)) == (400, "INVALID_NAME")
