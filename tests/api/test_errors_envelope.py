from collections.abc import Iterator

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from pydantic import BaseModel

from plot.api.app import create_app
from plot.api.deps import AppState
from plot.core.errors import DomainExists


class Body(BaseModel):
    years: int


@pytest.fixture
def probe_client(state: AppState) -> Iterator[TestClient]:
    app = create_app(state)
    router = APIRouter(prefix="/api/v1")

    @router.get("/conflict")
    def conflict() -> None:
        raise DomainExists(name="shop.com")

    @router.post("/body")
    def body(payload: Body) -> dict[str, int]:
        return {"years": payload.years}

    @router.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internals")

    app.include_router(router)
    with TestClient(app) as client:
        yield client


def test_plot_error_rendered_as_envelope(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/conflict")
    assert response.status_code == 409
    body = response.json()
    assert body == {
        "error": {
            "code": "DOMAIN_EXISTS",
            "message": "domain already registered",
            "details": {"name": "shop.com"},
        },
        "request_id": response.headers["X-Request-ID"],
    }


def test_request_validation_is_400_validation_error(probe_client: TestClient) -> None:
    response = probe_client.post("/api/v1/body", json={"years": "many"})
    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["errors"][0]["loc"] == ["body", "years"]
    malformed = probe_client.post(
        "/api/v1/body", content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert malformed.status_code == 400
    assert malformed.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unexpected_error_is_500_without_leaking(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/boom")
    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_client_request_id_is_kept_when_well_formed(probe_client: TestClient) -> None:
    response = probe_client.get("/api/v1/conflict", headers={"X-Request-ID": "abc-123"})
    assert response.json()["request_id"] == "abc-123"
    assert response.headers["X-Request-ID"] == "abc-123"
    replaced = probe_client.get("/api/v1/conflict", headers={"X-Request-ID": "bad id\n"})
    assert replaced.json()["request_id"] != "bad id\n"
    assert len(replaced.json()["request_id"]) == 32


def test_each_request_gets_distinct_id(probe_client: TestClient) -> None:
    first = probe_client.get("/api/v1/conflict").json()["request_id"]
    second = probe_client.get("/api/v1/conflict").json()["request_id"]
    assert first != second
