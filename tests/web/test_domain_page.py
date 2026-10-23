from datetime import UTC, datetime

from fastapi.testclient import TestClient

from plot.api.deps import AppState
from plot.cli.client import ApiClient
from plot.db.models import PendingChange
from plot.web import views
from tests.conftest import T0
from tests.fakes import FakeDnsPublisher

NS = ["ns1.myhost.net", "ns2.myhost.net"]


def test_detail_shows_registry_and_dns(ui: TestClient, api: ApiClient) -> None:
    api.post("/domains", {"name": "shop.com", "owner": "alice", "nameservers": NS})
    page = ui.get("/ui/domains/shop.com").text
    assert "<h1>shop.com</h1>" in page
    assert "<dt>Nameservers in DB</dt><dd>ns1.myhost.net, ns2.myhost.net</dd>" in page
    assert "<dt>Visible in DNS</dt><dd>no delegation</dd>" in page
    assert "/ui/history?domain=shop.com" in page


def test_unknown_domain_shows_error(ui: TestClient) -> None:
    page = ui.get("/ui/domains/nope.com").text
    assert "DOMAIN_NOT_FOUND: domain not found" in page


def test_pending_change_polls_until_in_sync(
    ui: TestClient, api: ApiClient, state: AppState
) -> None:
    api.post("/domains", {"name": "shop.com", "owner": "a"})
    assert 'hx-trigger="every 1s"' not in ui.get("/ui/domains/shop.com").text
    # FakeDnsPublisher records calls only; write a pending row like the real publisher does
    with state.sessions.begin() as session:
        session.add(
            PendingChange(domain_name="shop.com", snapshot=None, scheduled_at=T0, apply_at=T0)
        )
    fragment = ui.get("/ui/domains/shop.com/dns").text
    assert fragment.startswith('<section id="dns-panel"')
    assert 'hx-get="http://testserver/ui/domains/shop.com/dns" hx-trigger="every 1s"' in fragment
    assert "applies in 0s" in fragment


def test_actions_go_through_the_api(ui: TestClient, api: ApiClient, state: AppState) -> None:
    api.post("/domains", {"name": "shop.com", "owner": "a"})
    assert isinstance(state.publisher, FakeDnsPublisher)
    base = "/ui/domains/shop.com"
    assert "serverHold set" in ui.post(f"{base}/hold").text
    assert api.get("/domains/shop.com")["status"] == ["serverHold"]
    assert "Release hold" in ui.get(base).text
    ui.post(f"{base}/release")
    assert api.get("/domains/shop.com")["status"] == []
    assert "renewed for 2 year(s)" in ui.post(f"{base}/renew", data={"years": "2"}).text
    assert api.get("/domains/shop.com")["expires_at"].startswith("2029-")
    ui.post(f"{base}/nameservers", data={"nameservers": "ns1.myhost.net\r\nns2.myhost.net"})
    assert api.get("/domains/shop.com")["nameservers"] == NS
    ui.post(f"{base}/overrides", data={"delay": "20", "ttl": ""})
    assert api.get("/domains/shop.com")["overrides"] == {"propagation_delay": 20, "ns_ttl": None}
    ui.post(f"{base}/overrides", data={"delay": "none", "ttl": "60"})
    assert api.get("/domains/shop.com")["overrides"] == {"propagation_delay": None, "ns_ttl": 60}
    assert "expired" in ui.post(f"{base}/expire-now").text
    assert api.get("/domains/shop.com")["expired"] is True
    page = ui.post(f"{base}/delete")
    assert (
        "deleted shop.com" in page.text
        and str(page.url) == "http://testserver/ui/?notice=deleted+shop.com"
    )


def test_action_errors_are_flashed(ui: TestClient, api: ApiClient) -> None:
    api.post("/domains", {"name": "shop.com", "owner": "a"})
    base = "/ui/domains/shop.com"
    assert "RENEW_LIMIT" in ui.post(f"{base}/renew", data={"years": "10"}).text
    assert (
        "INVALID_NS_COUNT" in ui.post(f"{base}/nameservers", data={"nameservers": "ns1.x.net"}).text
    )
    assert "VALIDATION_ERROR" in ui.post(f"{base}/overrides", data={"delay": "soon"}).text
    api.post("/hosts", {"name": "ns1.shop.com", "ipv4": ["192.168.1.1"]})
    api.post(
        "/domains", {"name": "blog.com", "owner": "a", "nameservers": ["ns1.shop.com", "ns1.x.net"]}
    )
    response = ui.post(f"{base}/delete")
    assert "HOST_IN_USE" in response.text and "/ui/domains/shop.com" in str(response.url)


def test_view_helpers() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    domain = {
        "nameservers": NS,
        "dns_visible": {
            "published_at": "2025-12-31T23:59:00Z",
            "nameservers": ["old.ns.net"],
            "pending": [{"apply_at": "2026-01-01T00:00:12.300000Z"}],
        },
    }
    panel = views.dns_panel(domain, now)
    assert (panel.visible, panel.in_db, panel.pending_seconds, panel.in_sync) == (
        ["old.ns.net"],
        NS,
        [13],
        False,
    )
    assert views.relative("2025-12-31T23:59:00Z", now) == "60s ago"
    assert views.relative("2025-12-31T23:00:00Z", now) == "60m ago"
    assert views.relative("2025-12-01T00:00:00Z", now) == "2025-12-01 00:00:00 UTC"
    assert views.relative("2026-01-01T00:00:05Z", now) == "in 5s"
    assert views.relative(None) == "never"
    assert views.override_body("", "") == {}
    assert views.override_body("None", "30") == {"propagation_delay": None, "ns_ttl": 30}
    assert views.as_int("-1") == -1 and views.as_int("x") == "x"
