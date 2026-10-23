"""SPEC §16 P2 exit gate: every §8.1 error code is reachable and no endpoint exists outside §8.2."""

import re
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session
from starlette.routing import Route

from plot.api.app import API_PREFIX, create_app
from plot.api.deps import AppState
from plot.core import errors
from plot.core.clock import FakeClock
from tests.api.conftest import API_KEY
from tests.api.helpers import NS_PAIR, register

SPEC = Path(__file__).resolve().parents[2] / "docs" / "SPEC.md"


def spec_endpoints() -> set[tuple[str, str]]:
    section = SPEC.read_text(encoding="utf-8").split("### 8.2 Endpoints", 1)[1].split("###", 1)[0]
    endpoints = set()
    for methods, paths in re.findall(r"^\| ([A-Z /]+) \| (`[^|]+) \|", section, flags=re.M):
        for method in methods.split("/"):
            for path in re.findall(r"`([^`]+)`", paths):
                endpoints.add((method.strip(), API_PREFIX + path.split("?")[0]))
    return endpoints


def test_routes_match_spec_endpoints_exactly(state: AppState) -> None:
    app = create_app(state)
    documented = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }
    assert len(spec_endpoints()) == 22
    assert documented == spec_endpoints()
    # nothing reachable outside the documented API (no docs, no undocumented routes)
    assert not [r for r in app.routes if isinstance(r, (APIRoute, Route))]
    client = TestClient(app, headers={"X-API-Key": API_KEY})
    for path in ("/docs", "/redoc", "/openapi.json", "/health", "/api/v1/docs"):
        assert client.get(path).status_code == 404


def all_codes() -> set[str]:
    codes = set()
    stack: list[type[errors.PlotError]] = [errors.PlotError]
    while stack:
        cls = stack.pop()
        stack.extend(cls.__subclasses__())
        if not cls.__subclasses__():
            codes.add(cls.code)
    return codes


class ExplodingPublisher:
    def domains_changed(self, session: Session, domain_names: object) -> None:
        raise RuntimeError("pdns client bug")

    def reconcile(self, session: Session) -> list[str]:
        return []


Trigger = Callable[[TestClient, AppState], Response]


def _ns(client: TestClient, names: list[str]) -> Response:
    response: Response = client.put(
        "/api/v1/domains/shop.com/nameservers", json={"nameservers": names}
    )
    return response


def _purged(client: TestClient, state: AppState) -> Response:
    assert isinstance(state.clock, FakeClock)
    state.clock.advance(timedelta(days=400))
    response: Response = client.post("/api/v1/domains/shop.com/renew", json={"years": 1})
    return response


def _in_use(client: TestClient, state: AppState) -> Response:
    client.post("/api/v1/hosts", json={"name": "ns1.shop.com", "ipv4": ["192.168.1.10"]})
    register(client, "blog.com")
    client.put(
        "/api/v1/domains/blog.com/nameservers", json={"nameservers": ["ns1.shop.com", "ns1.x.net"]}
    )
    response: Response = client.delete("/api/v1/hosts/ns1.shop.com")
    return response


def _glue(client: TestClient, state: AppState) -> Response:
    client.delete("/api/v1/domains/shop.com")
    client.post("/api/v1/hosts", json={"name": "ns1.shop.com"})
    register(client)
    return _ns(client, ["ns1.shop.com", "ns1.x.net"])


def _internal(client: TestClient, state: AppState) -> Response:
    state.publisher = ExplodingPublisher()
    response: Response = client.post("/api/v1/domains", json={"name": "boom.com", "owner": "a"})
    assert client.get("/api/v1/domains/boom.com").status_code == 404  # rolled back
    return response


TRIGGERS: dict[str, tuple[int, Trigger]] = {
    "INVALID_NAME": (400, lambda c, s: c.get("/api/v1/domains/bad_name.com")),
    "NOT_REGISTRABLE": (
        400,
        lambda c, s: c.post("/api/v1/domains", json={"name": "a.b.com", "owner": "a"}),
    ),
    "TLD_NOT_SUPPORTED": (
        400,
        lambda c, s: c.post("/api/v1/domains", json={"name": "a.xyz", "owner": "a"}),
    ),
    "RESERVED_NAME": (
        400,
        lambda c, s: c.post("/api/v1/domains", json={"name": "github.com", "owner": "a"}),
    ),
    "INVALID_PERIOD": (
        400,
        lambda c, s: c.post("/api/v1/domains/shop.com/renew", json={"years": 0}),
    ),
    "INVALID_STATUS": (
        400,
        lambda c, s: c.put("/api/v1/domains/shop.com/status", json={"add": ["ok"]}),
    ),
    "INVALID_ADDRESS": (
        400,
        lambda c, s: c.post("/api/v1/hosts", json={"name": "ns1.shop.com", "ipv4": ["0.0.0.0"]}),
    ),
    "INVALID_NS_COUNT": (400, lambda c, s: _ns(c, ["ns1.x.net"])),
    "DUPLICATE_NS": (400, lambda c, s: _ns(c, ["ns1.x.net", "ns1.x.net"])),
    "HOST_ADDR_REQUIRED": (
        400,
        lambda c, s: c.post("/api/v1/hosts", json={"name": "ns1.shop.com"}),
    ),
    "HOST_ADDR_FORBIDDEN": (
        400,
        lambda c, s: c.post("/api/v1/hosts", json={"name": "ns1.x.net", "ipv4": ["192.168.1.1"]}),
    ),
    "GLUE_REQUIRED": (400, _glue),
    "VALIDATION_ERROR": (400, lambda c, s: c.post("/api/v1/domains", json={"name": "a.com"})),
    "UNAUTHORIZED": (401, lambda c, s: c.get("/api/v1/domains", headers={"X-API-Key": "nope"})),
    "DOMAIN_NOT_FOUND": (404, lambda c, s: c.get("/api/v1/domains/nope.com")),
    "HOST_NOT_FOUND": (404, lambda c, s: c.get("/api/v1/hosts/ns9.x.net")),
    "DOMAIN_EXISTS": (
        409,
        lambda c, s: c.post("/api/v1/domains", json={"name": "shop.com", "owner": "b"}),
    ),
    "HOST_EXISTS": (
        409,
        lambda c, s: (
            c.post("/api/v1/hosts", json={"name": "ns1.x.net"}),
            c.post("/api/v1/hosts", json={"name": "ns1.x.net"}),
        )[1],
    ),
    "HOST_IN_USE": (409, _in_use),
    "RENEW_LIMIT": (409, lambda c, s: c.post("/api/v1/domains/shop.com/renew", json={"years": 10})),
    "DOMAIN_PURGED": (410, _purged),
    "INTERNAL_ERROR": (500, _internal),
}


def test_trigger_table_covers_every_code() -> None:
    assert set(TRIGGERS) == all_codes()


@pytest.fixture
def seeded(state: AppState) -> Iterator[TestClient]:
    with TestClient(create_app(state), headers={"X-API-Key": API_KEY}) as client:
        register(client, nameservers=NS_PAIR)
        yield client


@pytest.mark.parametrize("code", sorted(TRIGGERS))
def test_every_error_code_is_reachable_through_the_api(
    seeded: TestClient, state: AppState, code: str
) -> None:
    status, trigger = TRIGGERS[code]
    response = trigger(seeded, state)
    assert response.status_code == status, response.text
    body = response.json()
    assert body["error"]["code"] == code
    assert set(body) == {"error", "request_id"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["request_id"] == response.headers["X-Request-ID"]


@pytest.mark.parametrize(
    ("method", "path"),
    sorted(e for e in spec_endpoints() if not e[1].endswith("/health")),
)
def test_every_protected_endpoint_requires_api_key(
    anon: TestClient, method: str, path: str
) -> None:
    response = anon.request(method, path.replace("{name}", "shop.com"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
