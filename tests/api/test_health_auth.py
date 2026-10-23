import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from plot.api.app import create_app
from plot.api.deps import AppState, require_api_key
from tests.api.conftest import API_KEY, set_probe


def test_health_ok_without_api_key(anon: TestClient) -> None:
    response = anon.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok", "pdns": "ok", "unbound": "ok"}
    assert len(response.headers["X-Request-ID"]) == 32


def test_health_degraded_when_dependency_down(anon: TestClient, state: AppState) -> None:
    set_probe(state, "pdns", lambda: False)

    def broken() -> bool:
        raise ConnectionError("unbound-control unreachable")

    set_probe(state, "unbound", broken)
    body = anon.get("/api/v1/health").json()
    assert body == {"status": "degraded", "db": "ok", "pdns": "down", "unbound": "down"}


def test_health_missing_probe_is_down(anon: TestClient, state: AppState) -> None:
    del state.health_probes["unbound"]
    assert anon.get("/api/v1/health").json()["unbound"] == "down"


def _app_with_protected_route(state: AppState) -> TestClient:
    app = create_app(state)
    router = APIRouter(prefix="/api/v1", dependencies=[Depends(require_api_key)])

    @router.get("/probe")
    def probe() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(router)
    return TestClient(app)


@pytest.mark.parametrize("headers", [{}, {"X-API-Key": ""}, {"X-API-Key": "wrong"}])
def test_protected_route_rejects_missing_or_wrong_key(
    state: AppState, headers: dict[str, str]
) -> None:
    response = _app_with_protected_route(state).get("/api/v1/probe", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert API_KEY not in response.text


def test_protected_route_accepts_key(state: AppState) -> None:
    response = _app_with_protected_route(state).get("/api/v1/probe", headers={"X-API-Key": API_KEY})
    assert response.status_code == 200


def test_no_docs_or_schema_routes(anon: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert anon.get(path).status_code == 404
