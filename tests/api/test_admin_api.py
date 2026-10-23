import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from plot.api.deps import AppState
from plot.db.models import Domain
from tests.api.helpers import NS_PAIR, error_code, register
from tests.fakes import FakeDnsPublisher, FakeResolverControl

DEFAULTS = {
    "propagation_delay": 0,
    "ns_ttl": 300,
    "default_years": 1,
    "expiry_grace_days": 30,
    "flush_on_apply": True,
}


def test_settings_get_and_partial_put(client: TestClient) -> None:
    assert client.get("/api/v1/admin/settings").json() == DEFAULTS
    body = client.put("/api/v1/admin/settings", json={"propagation_delay": 20, "default_years": 2})
    assert body.status_code == 200
    expected = {**DEFAULTS, "propagation_delay": 20, "default_years": 2}
    assert body.json() == expected
    assert client.get("/api/v1/admin/settings").json() == expected
    # the stored default_years is used by the next registration
    assert register(client)["expires_at"] == "2028-01-01T00:00:00Z"


@pytest.mark.parametrize(
    "body",
    [{"ns_ttl": -1}, {"default_years": 11}, {"ns_ttl": None}, {"flush_on_apply": "yes"}, {"x": 1}],
)
def test_settings_validation(client: TestClient, body: dict[str, object]) -> None:
    response = client.put("/api/v1/admin/settings", json=body)
    assert (response.status_code, error_code(response)) == (400, "VALIDATION_ERROR")
    assert client.get("/api/v1/admin/settings").json() == DEFAULTS


def test_expire_now(client: TestClient) -> None:
    register(client, nameservers=NS_PAIR)
    body = client.post("/api/v1/admin/domains/shop.com/expire-now").json()
    assert body["expired"] is True
    response = client.post("/api/v1/admin/domains/nope.com/expire-now")
    assert (response.status_code, error_code(response)) == (404, "DOMAIN_NOT_FOUND")


def _mark_seed(sessions: sessionmaker[Session], name: str) -> None:
    with sessions.begin() as session:
        session.execute(update(Domain).where(Domain.name == name).values(seed=True))


def test_reset_by_prefix(client: TestClient, state: AppState) -> None:
    register(client, "scn-a.com", nameservers=["scn-ns1.other.net", "scn-ns2.other.net"])
    register(client, "scn-b.com")
    register(client, "keep.com")
    client.post("/api/v1/hosts", json={"name": "scn-lonely.other.net"})
    body = client.post("/api/v1/admin/reset", json={"prefix": "SCN-"}).json()
    assert body == {
        "deleted_domains": ["scn-a.com", "scn-b.com"],
        "deleted_hosts": ["scn-lonely.other.net"],
    }
    assert [d["name"] for d in client.get("/api/v1/domains").json()["items"]] == ["keep.com"]
    assert client.get("/api/v1/hosts").json()["items"] == []
    assert isinstance(state.resolver, FakeResolverControl)
    assert state.resolver.flushed == [None]
    assert isinstance(state.publisher, FakeDnsPublisher)
    assert {"scn-a.com", "scn-b.com"} <= state.publisher.changed


def test_reset_all_keeps_seed(client: TestClient, sessions: sessionmaker[Session]) -> None:
    register(client, "myhost.net")
    client.post("/api/v1/hosts", json={"name": "ns1.myhost.net", "ipv4": ["172.28.0.31"]})
    client.post("/api/v1/hosts", json={"name": "ns2.myhost.net", "ipv4": ["172.28.0.32"]})
    client.put("/api/v1/domains/myhost.net/nameservers", json={"nameservers": NS_PAIR})
    _mark_seed(sessions, "myhost.net")
    register(client, "shop.com", nameservers=NS_PAIR)
    register(client, "blog.com", nameservers=["ns1.other.net", "ns2.other.net"])
    body = client.post("/api/v1/admin/reset", json={"all": True}).json()
    assert body == {"deleted_domains": ["blog.com", "shop.com"], "deleted_hosts": []}
    assert [d["name"] for d in client.get("/api/v1/domains").json()["items"]] == ["myhost.net"]
    assert [h["name"] for h in client.get("/api/v1/hosts").json()["items"]] == NS_PAIR
    assert client.get("/api/v1/hosts/ns1.myhost.net").json()["used_by"] == ["myhost.net"]


@pytest.mark.parametrize(
    "body", [{}, {"prefix": ""}, {"prefix": "  "}, {"prefix": "scn-", "all": True}, {"all": False}]
)
def test_reset_needs_exactly_one_selector(client: TestClient, body: dict[str, object]) -> None:
    register(client)
    response = client.post("/api/v1/admin/reset", json=body)
    assert (response.status_code, error_code(response)) == (400, "VALIDATION_ERROR")
    assert client.get("/api/v1/domains/shop.com").status_code == 200


def test_resolver_flush(client: TestClient, state: AppState) -> None:
    assert client.post("/api/v1/admin/resolver/flush", json={"domain": "Shop.COM."}).json() == {
        "flushed": "shop.com"
    }
    assert client.post("/api/v1/admin/resolver/flush").json() == {"flushed": None}
    assert client.post("/api/v1/admin/resolver/flush", json={}).json() == {"flushed": None}
    assert isinstance(state.resolver, FakeResolverControl)
    assert state.resolver.flushed == ["shop.com", None, None]
    response = client.post("/api/v1/admin/resolver/flush", json={"domain": "bad_name.com"})
    assert (response.status_code, error_code(response)) == (400, "INVALID_NAME")


def test_reconcile_calls_publisher(client: TestClient, state: AppState) -> None:
    assert client.post("/api/v1/admin/publish/reconcile").json() == {"fixed": []}
    assert isinstance(state.publisher, FakeDnsPublisher)
    assert state.publisher.reconciled == 1


def test_admin_requires_key(anon: TestClient) -> None:
    for method, path in [
        ("GET", "/api/v1/admin/settings"),
        ("POST", "/api/v1/admin/reset"),
        ("POST", "/api/v1/admin/resolver/flush"),
        ("POST", "/api/v1/admin/publish/reconcile"),
    ]:
        response = anon.request(method, path)
        assert (response.status_code, error_code(response)) == (401, "UNAUTHORIZED")
