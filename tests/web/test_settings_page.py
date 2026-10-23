from fastapi.testclient import TestClient

from plot.api.deps import AppState
from plot.cli.client import ApiClient
from tests.fakes import FakeResolverControl


def test_settings_show_and_save(ui: TestClient, api: ApiClient) -> None:
    page = ui.get("/ui/settings").text
    assert 'name="ns_ttl" type="number" min="0" value="300"' in page
    assert "checked" in page
    form = {
        "propagation_delay": "20",
        "ns_ttl": "60",
        "default_years": "2",
        "expiry_grace_days": "5",
    }
    assert "settings saved" in ui.post("/ui/settings", data=form).text  # checkbox off
    assert api.get("/admin/settings") == {
        "propagation_delay": 20,
        "ns_ttl": 60,
        "default_years": 2,
        "expiry_grace_days": 5,
        "flush_on_apply": False,
    }
    ui.post("/ui/settings", data={**form, "flush_on_apply": "on"})
    assert api.get("/admin/settings")["flush_on_apply"] is True
    assert "VALIDATION_ERROR" in ui.post("/ui/settings", data={"default_years": "11"}).text


def test_flush_and_reset(ui: TestClient, api: ApiClient, state: AppState) -> None:
    assert "flushed shop.com" in ui.post("/ui/settings/flush", data={"domain": "shop.com"}).text
    assert (
        "flushed the whole resolver cache"
        in ui.post("/ui/settings/flush", data={"domain": ""}).text
    )
    assert isinstance(state.resolver, FakeResolverControl)
    assert state.resolver.flushed == ["shop.com", None]
    api.post("/domains", {"name": "scn-a.com", "owner": "a"})
    api.post("/domains", {"name": "keep.com", "owner": "a"})
    assert "reset done" in ui.post("/ui/settings/reset", data={"prefix": "scn-"}).text
    assert [d["name"] for d in api.get("/domains")["items"]] == ["keep.com"]
    assert "VALIDATION_ERROR" in ui.post("/ui/settings/reset", data={}).text
    ui.post("/ui/settings/reset", data={"all": "on"})
    assert api.get("/domains")["items"] == []
