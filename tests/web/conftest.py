"""Web UI tests: the UI app calls the API app in-process through ApiClient."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from plot.api.app import create_app
from plot.api.deps import AppState
from plot.cli.client import ApiClient
from plot.web.app import mount_web_ui
from tests.api.conftest import API_KEY, sessions, state  # noqa: F401  (fixtures)


@pytest.fixture
def app_client(state: AppState) -> Iterator[TestClient]:  # noqa: F811
    app = create_app(state)
    mount_web_ui(app, lambda key: ApiClient(TestClient(app, headers={"X-API-Key": key})))
    with TestClient(app) as client:
        yield client


@pytest.fixture
def ui(app_client: TestClient) -> TestClient:
    """Logged-in browser."""
    response = app_client.post("/ui/login", data={"api_key": API_KEY})
    assert response.status_code == 200, response.text
    return app_client


@pytest.fixture
def api(state: AppState) -> Iterator[ApiClient]:  # noqa: F811
    with TestClient(create_app(state), headers={"X-API-Key": API_KEY}) as client:
        yield ApiClient(client)
