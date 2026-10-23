from fastapi.testclient import TestClient

from plot.cli.client import ApiClient
from tests.api.conftest import API_KEY


def test_requires_login(app_client: TestClient) -> None:
    response = app_client.get("/ui/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].endswith("/ui/login")
    assert "API key" in app_client.get("/ui/login").text


def test_wrong_key_is_rejected(app_client: TestClient) -> None:
    response = app_client.post("/ui/login", data={"api_key": "nope"})
    assert "UNAUTHORIZED" in response.text
    assert "plot_api_key" not in app_client.cookies


def test_login_sets_httponly_cookie_and_logout_clears_it(app_client: TestClient) -> None:
    response = app_client.post("/ui/login", data={"api_key": API_KEY}, follow_redirects=False)
    assert response.status_code == 303
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    app_client.cookies.set("plot_api_key", API_KEY)
    assert API_KEY not in app_client.get("/ui/").text
    logout = app_client.post("/ui/logout", follow_redirects=False)
    assert logout.headers["location"].endswith("/ui/login?notice=logged+out")


def test_stale_cookie_goes_back_to_login(app_client: TestClient) -> None:
    app_client.cookies.set("plot_api_key", "revoked")
    response = app_client.get("/ui/", follow_redirects=False)
    assert response.headers["location"].endswith("/ui/login")


def test_domain_list_shows_db_and_dns_state(ui: TestClient, api: ApiClient) -> None:
    api.post(
        "/domains",
        {"name": "shop.com", "owner": "alice", "nameservers": ["ns1.myhost.net", "ns2.myhost.net"]},
    )
    api.post("/domains", {"name": "blog.com", "owner": "bob"})
    page = ui.get("/ui/").text
    assert '<a href="http://testserver/ui/domains/shop.com">shop.com</a>' in page
    assert "ns1.myhost.net, ns2.myhost.net" in page
    assert "htmx.min.js" in page and 'hx-boost="true"' in page
    filtered = ui.get("/ui/", params={"owner": "bob"}).text
    assert "/ui/domains/blog.com" in filtered and "/ui/domains/shop.com" not in filtered


def test_register_form_uses_api_and_redirects(ui: TestClient, api: ApiClient) -> None:
    response = ui.post(
        "/ui/domains",
        data={
            "name": "Shop.COM",
            "owner": "",
            "years": "2",
            "nameservers": "ns1.myhost.net\nns2.myhost.net",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/ui/domains/Shop.COM?notice=registered+Shop.COM")
    domain = api.get("/domains/shop.com")
    assert (domain["owner"], domain["nameservers"]) == ("web", ["ns1.myhost.net", "ns2.myhost.net"])
    assert domain["expires_at"].startswith("2028-")


def test_register_error_is_shown(ui: TestClient) -> None:
    page = ui.post("/ui/domains", data={"name": "github.com"}).text
    assert "RESERVED_NAME: name is reserved" in page
    page = ui.post("/ui/domains", data={"name": "x.com", "years": "many"}).text
    assert "VALIDATION_ERROR" in page


def test_static_assets(app_client: TestClient) -> None:
    assert app_client.get("/ui/static/htmx.min.js").text.startswith("var htmx=")
    assert "--accent" in app_client.get("/ui/static/style.css").text
