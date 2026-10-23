from collections.abc import Callable

import httpx
import pytest
from typer.testing import CliRunner

from plot.cli.client import ApiClient, ApiError
from plot.cli.main import app


def mock(handler: Callable[[httpx.Request], httpx.Response]) -> ApiClient:
    transport = httpx.MockTransport(handler)
    return ApiClient(httpx.Client(base_url="http://registrar", transport=transport))


def test_envelope_becomes_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/domains/x.com"
        return httpx.Response(
            404,
            json={
                "error": {"code": "DOMAIN_NOT_FOUND", "message": "domain not found", "details": {}}
            },
        )

    with pytest.raises(ApiError) as err:
        mock(handler).get("/domains/x.com")
    assert (err.value.code, err.value.message, err.value.status) == (
        "DOMAIN_NOT_FOUND",
        "domain not found",
        404,
    )


def test_non_envelope_error_and_204_and_query_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.url.params.get("owner") == "a":
            assert "prefix" not in request.url.params  # None values are dropped
            return httpx.Response(200, json={"items": []})
        return httpx.Response(502, text="bad gateway")

    client = mock(handler)
    assert client.delete("/domains/x.com") is None
    assert client.get("/domains", owner="a", prefix=None) == {"items": []}
    with pytest.raises(ApiError, match="HTTP_ERROR: HTTP 502"):
        client.get("/domains")


def test_unreachable_api() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ApiError) as err:
        mock(handler).get("/domains")
    assert err.value.code == "CONNECTION_ERROR"


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLOT_API_URL", "http://192.168.1.175:8080/")
    monkeypatch.setenv("PLOT_API_KEY", "secret")
    client = ApiClient.from_env()
    assert str(client.http.base_url) == "http://192.168.1.175:8080"
    assert client.http.headers["X-API-Key"] == "secret"
    monkeypatch.delenv("PLOT_API_URL")
    assert str(ApiClient.from_env().http.base_url) == "http://localhost:8080"


def test_help_and_usage_error_exit_codes() -> None:
    runner = CliRunner()
    assert runner.invoke(app, ["--help"]).exit_code == 0
    assert runner.invoke(app, ["no-such-command"]).exit_code == 2


def test_is_registered() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        name = request.url.params["name"]
        if name == "down.com":
            return httpx.Response(500, text="boom")
        reasons = {"shop.com": "DOMAIN_EXISTS", "github.com": "RESERVED_NAME"}
        reason = reasons.get(name)
        body = {"name": name, "available": reason is None, **({"reason": reason} if reason else {})}
        return httpx.Response(200, json=body)

    client = mock(handler)
    assert client.is_registered("shop.com") is True
    assert client.is_registered("free.com") is False
    assert client.is_registered("github.com") is False
    assert client.is_registered("down.com") is None


def test_call_returns_status_and_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            return httpx.Response(201, json={"ok": True})
        return httpx.Response(204)

    client = mock(handler)
    assert client.call("POST", "/domains", json={}) == (201, {"ok": True})
    assert client.call("DELETE", "/domains/x.com") == (204, None)
