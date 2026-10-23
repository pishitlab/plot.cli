from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from plot.api.app import create_app
from plot.api.deps import AppState
from plot.cli.client import ApiClient
from plot.web.app import mount_web_ui
from tests.api.conftest import API_KEY
from tests.cli.test_scenario_cli import FakeEngine


@pytest.fixture
def engine() -> FakeEngine:
    return FakeEngine(failing={"S08"})


@pytest.fixture
def scenario_ui(state: AppState, engine: FakeEngine) -> Iterator[TestClient]:
    app = create_app(state)
    clients: list[ApiClient] = []

    def client_for_key(key: str) -> ApiClient:
        clients.append(ApiClient(TestClient(app, headers={"X-API-Key": key})))
        return clients[-1]

    def engine_for(api: ApiClient) -> FakeEngine:
        assert api is clients[-1]  # the engine uses the logged-in user's API client
        return engine

    mount_web_ui(app, client_for_key, engine_for)
    with TestClient(app) as browser:
        browser.post("/ui/login", data={"api_key": API_KEY})
        yield browser


def test_catalog_listed(scenario_ui: TestClient) -> None:
    page = scenario_ui.get("/ui/scenarios").text
    assert page.count('name="id" value="S') == 16
    assert "propagation delay" in page and "Run all" in page


def test_run_one_and_all(scenario_ui: TestClient, engine: FakeEngine) -> None:
    page = scenario_ui.post("/ui/scenarios/run", data={"id": "S01"}).text
    assert "S01 happy path (external NS)" in page and '<span class="tag ok">PASS</span>' in page
    assert engine.ran == ["S01"]
    page = scenario_ui.post("/ui/scenarios/run", data={"id": "all"}).text
    assert len(engine.ran) == 17
    assert page.count('<span class="tag bad">FAIL</span>') == 1
    assert "verifier said MISMATCH" in page


def test_unknown_scenario(scenario_ui: TestClient, engine: FakeEngine) -> None:
    assert (
        "unknown scenario &#39;S99&#39;"
        in scenario_ui.post("/ui/scenarios/run", data={"id": "S99"}).text
    )
    assert engine.ran == []


def test_scenarios_need_login(app_client: TestClient) -> None:
    response = app_client.get("/ui/scenarios", follow_redirects=False)
    assert response.headers["location"].endswith("/ui/login")
