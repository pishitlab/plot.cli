"""HTTP client of the registrar API used by every ``plot`` command except ``seed``."""

import os
from typing import Any

import httpx

DEFAULT_API_URL = "http://localhost:8080"
API_PREFIX = "/api/v1"


class ApiError(Exception):
    """An error envelope from the API (SPEC §8.1), or the API being unreachable."""

    def __init__(self, code: str, message: str, status: int | None = None) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.status = status


class ApiClient:
    """``api_key`` is sent with each request, so one pooled ``http`` client can serve many
    keys (the Web UI); the CLI puts the key in the client's default headers instead."""

    def __init__(self, http: httpx.Client, api_key: str | None = None) -> None:
        self.http = http
        self.api_key = api_key

    @classmethod
    def from_env(cls) -> "ApiClient":
        base = os.environ.get("PLOT_API_URL", DEFAULT_API_URL).rstrip("/")
        key = os.environ.get("PLOT_API_KEY", "")
        return cls(httpx.Client(base_url=base, headers={"X-API-Key": key}, timeout=30))

    def call(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> tuple[int, Any]:
        """Raw call: (HTTP status, parsed body or None). Raises only when unreachable."""
        try:
            headers = {"X-API-Key": self.api_key} if self.api_key is not None else None
            response = self.http.request(
                method, API_PREFIX + path, json=json, params=params, headers=headers
            )
        except httpx.HTTPError as err:
            raise ApiError("CONNECTION_ERROR", f"cannot reach the registrar API: {err}") from err
        try:
            body = response.json() if response.content else None
        except ValueError:
            body = None
        return response.status_code, body

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Body of a successful call; an error envelope is raised as ``ApiError``."""
        status, body = self.call(method, path, json=json, params=params)
        if status >= 400:
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict):
                raise ApiError(error["code"], error["message"], status)
            raise ApiError("HTTP_ERROR", f"HTTP {status}", status)
        return body

    def is_registered(self, name: str) -> bool | None:
        """Whether the registry holds ``name``; ``None`` when the API cannot say (A-025)."""
        try:
            check = self.get("/domains/check", name=name)
        except ApiError:
            return None
        return bool(not check["available"] and check.get("reason") == "DOMAIN_EXISTS")

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, json=body)

    def put(self, path: str, body: Any) -> Any:
        return self.request("PUT", path, json=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)
