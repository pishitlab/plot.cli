"""SPEC §16 P6: every page loads; the UI only reaches the system through the API client."""

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plot.cli.client import ApiClient
from plot.web import views

WEB = Path(__file__).resolve().parents[2] / "src" / "plot" / "web"


def test_history_page(ui: TestClient, api: ApiClient) -> None:
    api.post("/domains", {"name": "shop.com", "owner": "a"})
    ui.post("/ui/domains/shop.com/renew", data={"years": "1"})
    page = ui.get("/ui/history", params={"domain": "shop.com"}).text
    assert page.index("domain.renew") < page.index("domain.register")  # newest first
    assert "<code>expires_at</code>" in page
    assert "DOMAIN_NOT_FOUND" in ui.get("/ui/history", params={"domain": "nope.com"}).text
    assert "No events" not in ui.get("/ui/history").text  # just the form


def test_event_row_lists_changed_fields() -> None:
    row = views.event_row(
        {"action": "x", "before": {"a": 1, "b": 2}, "after": {"a": 1, "b": 3, "c": 4}}
    )
    assert row["changes"] == [("b", 2, 3), ("c", None, 4)]
    assert views.event_row({"before": None, "after": None})["changes"] == []


@pytest.mark.parametrize(
    "path",
    [
        "/ui/",
        "/ui/domains/shop.com",
        "/ui/domains/shop.com/dns",
        "/ui/hosts",
        "/ui/settings",
        "/ui/scenarios",
        "/ui/history",
        "/ui/history?domain=shop.com",
    ],
)
def test_every_page_loads(ui: TestClient, api: ApiClient, path: str) -> None:
    api.post(
        "/domains",
        {"name": "shop.com", "owner": "a", "nameservers": ["ns1.myhost.net", "ns2.myhost.net"]},
    )
    response = ui.get(path)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'role="alert"' not in response.text


@pytest.mark.parametrize(
    "path", ["/ui/", "/ui/hosts", "/ui/settings", "/ui/scenarios", "/ui/history"]
)
def test_every_page_needs_login(app_client: TestClient, path: str) -> None:
    response = app_client.get(path, follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"].endswith("/ui/login")


def test_web_ui_has_no_business_logic_of_its_own() -> None:
    """All actions go through ApiClient (the CLI's API client); no direct DB/service access."""
    forbidden = ("plot.services", "plot.db", "plot.dns", "plot.api", "plot.core")
    for path in WEB.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            modules = []
            if isinstance(node, ast.Import):
                modules = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules = [node.module]
            for module in modules:
                assert not module.startswith(forbidden), f"{path.name} imports {module}"
