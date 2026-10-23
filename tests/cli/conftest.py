"""CLI tests run `plot` with Typer's CliRunner against the API app in-process."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner, Result

from plot.api.app import create_app
from plot.api.deps import AppState
from plot.cli import output
from plot.cli.client import ApiClient
from plot.cli.main import app
from tests.api.conftest import API_KEY, sessions, state  # noqa: F401  (fixtures)


@pytest.fixture
def api_client(state: AppState) -> Iterator[TestClient]:  # noqa: F811
    with TestClient(create_app(state), headers={"X-API-Key": API_KEY}) as client:
        yield client


@pytest.fixture(autouse=True)
def wire_cli(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output, "client_factory", lambda: ApiClient(api_client))


class Plot:
    def __init__(self) -> None:
        self.runner = CliRunner()

    def __call__(self, *args: str) -> Result:
        return self.runner.invoke(app, list(args))


@pytest.fixture
def plot() -> Plot:
    return Plot()
