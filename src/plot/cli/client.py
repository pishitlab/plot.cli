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
    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    @classmethod
    def from_env(cls) -> "ApiClient":
        base = os.environ.get("PLOT_API_URL", DEFAULT_API_URL).rstrip("/")
        key = os.environ.get("PLOT_API_KEY", "")
        return cls(httpx.Client(base_url=base, headers={"X-API-Key": key}, timeout=30))

    def request(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = self.http.request(method, API_PREFIX + path, json=json, params=params)
        except httpx.HTTPError as err:
            raise ApiError("CONNECTION_ERROR", f"cannot reach the registrar API: {err}") from err
        if response.status_code == 204:
            return None
        try:
            body = response.json()
        except ValueError:
            body = None
        if response.status_code >= 400:
            error = body.get("error") if isinstance(body, dict) else None
            if isinstance(error, dict):
                raise ApiError(error["code"], error["message"], response.status_code)
            raise ApiError("HTTP_ERROR", f"HTTP {response.status_code}", response.status_code)
        return body

    def get(self, path: str, **params: Any) -> Any:
        return self.request("GET", path, params={k: v for k, v in params.items() if v is not None})

    def post(self, path: str, body: Any = None) -> Any:
        return self.request("POST", path, json=body)

    def put(self, path: str, body: Any) -> Any:
        return self.request("PUT", path, json=body)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path)
