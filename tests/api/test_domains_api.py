from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from plot.api.deps import AppState
from plot.core.clock import FakeClock
from plot.db.models import PendingChange, PublishedState
from tests.api.helpers import NS_PAIR, error_code, register
from tests.conftest import T0
from tests.fakes import FakeDnsPublisher


def test_check_available_and_taken(client: TestClient) -> None:
    assert client.get("/api/v1/domains/check", params={"name": "Shop.COM"}).json() == {
        "name": "shop.com",
        "available": True,
    }
    register(client)
    assert client.get("/api/v1/domains/check", params={"name": "shop.com"}).json() == {
        "name": "shop.com",
        "available": False,
        "reason": "DOMAIN_EXISTS",
    }


def test_check_requires_name(client: TestClient) -> None:
    response = client.get("/api/v1/domains/check")
    assert response.status_code == 400
    assert error_code(response) == "VALIDATION_ERROR"


def test_create_returns_domain_shape(client: TestClient, state: AppState) -> None:
    body = register(client, " Shop.COM. ", years=2, nameservers=NS_PAIR)
    assert body == {
        "name": "shop.com",
        "owner": "alice",
        "status": [],
        "expired": False,
        "created_at": "2026-01-01T00:00:00Z",
        "expires_at": "2028-01-01T00:00:00Z",
        "nameservers": NS_PAIR,
        "overrides": {"propagation_delay": None, "ns_ttl": None},
        "dns_visible": {"published_at": None, "nameservers": [], "pending": []},
    }
    assert isinstance(state.publisher, FakeDnsPublisher)
    assert state.publisher.changed == {"shop.com"}


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"name": "bad_name.com", "owner": "a"}, 400, "INVALID_NAME"),
        ({"name": "www.shop.com", "owner": "a"}, 400, "NOT_REGISTRABLE"),
        ({"name": "shop.xyz", "owner": "a"}, 400, "TLD_NOT_SUPPORTED"),
        ({"name": "github.com", "owner": "a"}, 400, "RESERVED_NAME"),
        ({"name": "shop.com", "owner": "a", "years": 11}, 400, "INVALID_PERIOD"),
        ({"name": "shop.com", "owner": "a", "nameservers": ["ns1.x.net"]}, 400, "INVALID_NS_COUNT"),
        (
            {"name": "shop.com", "owner": "a", "nameservers": ["ns1.x.net", "NS1.x.net."]},
            400,
            "DUPLICATE_NS",
        ),
        (
            {"name": "shop.com", "owner": "a", "nameservers": ["ns1.shop.com", "ns1.x.net"]},
            404,
            "HOST_NOT_FOUND",
        ),
        ({"name": "shop.com"}, 400, "VALIDATION_ERROR"),
        ({"name": "shop.com", "owner": "a", "years": "2"}, 400, "VALIDATION_ERROR"),
        ({"name": "shop.com", "owner": "a", "extra": 1}, 400, "VALIDATION_ERROR"),
        ({"name": "shop.com", "owner": " "}, 400, "VALIDATION_ERROR"),
    ],
)
def test_create_errors(client: TestClient, body: dict[str, object], status: int, code: str) -> None:
    response = client.post("/api/v1/domains", json=body)
    assert (response.status_code, error_code(response)) == (status, code)


def test_create_duplicate_is_409(client: TestClient) -> None:
    register(client)
    response = client.post("/api/v1/domains", json={"name": "SHOP.com", "owner": "bob"})
    assert (response.status_code, error_code(response)) == (409, "DOMAIN_EXISTS")


def test_failed_create_rolls_back(client: TestClient) -> None:
    response = client.post(
        "/api/v1/domains",
        json={"name": "shop.com", "owner": "a", "nameservers": ["ns1.shop.com", "ns1.x.net"]},
    )
    assert response.status_code == 404
    assert client.get("/api/v1/domains/shop.com").status_code == 404
    assert client.get("/api/v1/domains/check", params={"name": "shop.com"}).json()["available"]


def test_get_includes_dns_visible(client: TestClient, sessions: sessionmaker[Session]) -> None:
    register(client, nameservers=NS_PAIR)
    with sessions.begin() as session:
        session.add(
            PublishedState(
                domain_name="shop.com", snapshot={"nameservers": ["old.ns.net"]}, published_at=T0
            )
        )
        session.add(
            PendingChange(
                domain_name="shop.com",
                snapshot={"nameservers": NS_PAIR},
                scheduled_at=T0,
                apply_at=T0 + timedelta(seconds=20),
            )
        )
    body = client.get("/api/v1/domains/SHOP.com").json()
    assert body["nameservers"] == NS_PAIR
    assert body["dns_visible"] == {
        "published_at": "2026-01-01T00:00:00Z",
        "nameservers": ["old.ns.net"],
        "pending": [{"apply_at": "2026-01-01T00:00:20Z"}],
    }


def test_get_errors(client: TestClient) -> None:
    response = client.get("/api/v1/domains/nope.com")
    assert (response.status_code, error_code(response)) == (404, "DOMAIN_NOT_FOUND")
    response = client.get("/api/v1/domains/bad_name.com")
    assert (response.status_code, error_code(response)) == (400, "INVALID_NAME")


def test_get_purged_is_410(client: TestClient, state: AppState) -> None:
    register(client)
    assert isinstance(state.clock, FakeClock)
    state.clock.advance(timedelta(days=365 + 31))
    response = client.get("/api/v1/domains/shop.com")
    assert (response.status_code, error_code(response)) == (410, "DOMAIN_PURGED")


def test_list_with_filters_and_cursor(client: TestClient) -> None:
    for name in ["b.com", "a.com", "c.net"]:
        register(client, name)
    first = client.get("/api/v1/domains", params={"limit": 2}).json()
    assert [d["name"] for d in first["items"]] == ["a.com", "b.com"]
    assert first["next_cursor"] == "b.com"
    rest = client.get("/api/v1/domains", params={"cursor": first["next_cursor"]}).json()
    assert ([d["name"] for d in rest["items"]], rest["next_cursor"]) == (["c.net"], None)
    assert [d["name"] for d in client.get("/api/v1/domains?prefix=c").json()["items"]] == ["c.net"]
    assert client.get("/api/v1/domains?owner=nobody").json() == {"items": [], "next_cursor": None}


@pytest.mark.parametrize("limit", [0, 201, "x"])
def test_list_limit_validated(client: TestClient, limit: object) -> None:
    response = client.get("/api/v1/domains", params={"limit": limit})
    assert (response.status_code, error_code(response)) == (400, "VALIDATION_ERROR")


def test_delete(client: TestClient) -> None:
    register(client)
    response = client.delete("/api/v1/domains/shop.com")
    assert response.status_code == 204 and response.content == b""
    assert client.get("/api/v1/domains/shop.com").status_code == 404
    response = client.delete("/api/v1/domains/shop.com")
    assert (response.status_code, error_code(response)) == (404, "DOMAIN_NOT_FOUND")


def test_renew(client: TestClient) -> None:
    register(client)
    body = client.post("/api/v1/domains/shop.com/renew", json={"years": 2}).json()
    assert body["expires_at"] == "2029-01-01T00:00:00Z"


@pytest.mark.parametrize(
    ("years", "status", "code"),
    [(0, 400, "INVALID_PERIOD"), (10, 409, "RENEW_LIMIT"), ("1", 400, "VALIDATION_ERROR")],
)
def test_renew_errors(client: TestClient, years: object, status: int, code: str) -> None:
    register(client)
    response = client.post("/api/v1/domains/shop.com/renew", json={"years": years})
    assert (response.status_code, error_code(response)) == (status, code)
