import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from typer.testing import CliRunner

from plot.cli.main import app
from plot.core.errors import HostAddrForbidden, ReservedName, ValidationFailed
from plot.db.models import Domain
from plot.dns.demo_ns import DemoNs, DemoNsError
from plot.services.context import ServiceContext
from plot.services.domains import DomainService
from plot.services.hosts import HostService
from plot.services.seed import seed_provider
from tests.fakes import FakeDnsPublisher

CONFIG = Path(__file__).resolve().parents[2] / "config"


def test_seed_registers_domain_hosts_and_delegation(
    ctx: ServiceContext, publisher: FakeDnsPublisher
) -> None:
    view = seed_provider(ctx, "MyHost.NET", ["172.28.0.31", "172.28.0.32"])
    assert view.nameservers == ["ns1.myhost.net", "ns2.myhost.net"]
    assert HostService(ctx).get("ns2.myhost.net").ipv4 == ["172.28.0.32"]
    domain = DomainService(ctx).load("myhost.net")
    assert domain.seed and domain.owner == "seed"
    assert "myhost.net" in publisher.changed


def test_seed_is_idempotent_and_updates_addresses(ctx: ServiceContext) -> None:
    seed_provider(ctx, "myhost.net", ["172.28.0.31", "172.28.0.32"])
    view = seed_provider(ctx, "myhost.net", ["192.168.1.176", "2001:db8::177"])
    hosts = HostService(ctx)
    assert hosts.get("ns1.myhost.net").ipv4 == ["192.168.1.176"]
    assert (hosts.get("ns2.myhost.net").ipv4, hosts.get("ns2.myhost.net").ipv6) == (
        [],
        ["2001:db8::177"],
    )
    assert view.nameservers == ["ns1.myhost.net", "ns2.myhost.net"]
    assert ctx.session.query(Domain).count() == 1


def test_seed_survives_reset(ctx: ServiceContext) -> None:
    seed_provider(ctx, "myhost.net", ["172.28.0.31", "172.28.0.32"])
    DomainService(ctx).register(
        "shop.com", owner="a", nameservers=["ns1.myhost.net", "ns2.myhost.net"]
    )
    result = DomainService(ctx).reset(everything=True)
    assert result.deleted_domains == ["shop.com"]
    assert DomainService(ctx).get("myhost.net").nameservers == ["ns1.myhost.net", "ns2.myhost.net"]


def test_seed_refuses_to_reclassify_external_host(ctx: ServiceContext) -> None:
    DomainService(ctx).register(
        "shop.com", owner="a", nameservers=["ns1.myhost.net", "ns2.myhost.net"]
    )
    with pytest.raises(HostAddrForbidden, match="external host") as err:
        seed_provider(ctx, "myhost.net", ["172.28.0.31", "172.28.0.32"])
    assert err.value.details["used_by"] == ["shop.com"]


def test_seed_validates(ctx: ServiceContext) -> None:
    with pytest.raises(ValidationFailed):
        seed_provider(ctx, "myhost.net", [])
    with pytest.raises(ReservedName):
        seed_provider(ctx, "github.com", ["172.28.0.31"])


class FakeDemoApi:
    def __init__(self, existing: bool = False, fail: bool = False) -> None:
        self.existing = existing
        self.fail = fail
        self.requests: list[tuple[str, str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        self.requests.append((request.method, request.url.path, body))
        if self.fail:
            return httpx.Response(500, json={"error": "boom"})
        if request.method == "GET":
            return httpx.Response(200 if self.existing else 404, json={})
        return httpx.Response(201 if request.method == "POST" else 204)


def test_demo_ns_creates_zone_on_every_instance() -> None:
    fake = FakeDemoApi()
    demo = DemoNs(["http://ns1:8081", "http://ns2:8081"], "k", transport=httpx.MockTransport(fake))
    demo.ensure_zone(
        "myhost.net", ["ns1.myhost.net", "ns2.myhost.net"], {"ns1.myhost.net": "172.28.0.31"}
    )
    assert [m for m, _, _ in fake.requests] == ["GET", "POST", "PATCH"] * 2
    post = fake.requests[1][2]
    assert post == {
        "name": "myhost.net.",
        "kind": "Native",
        "nameservers": ["ns1.myhost.net.", "ns2.myhost.net."],
    }
    patch = fake.requests[2][2]["rrsets"]
    assert [(r["name"], r["type"]) for r in patch] == [
        ("myhost.net.", "NS"),
        ("ns1.myhost.net.", "A"),
    ]


def test_demo_ns_existing_zone_is_patched_only() -> None:
    fake = FakeDemoApi(existing=True)
    DemoNs(["http://ns1:8081"], "k", transport=httpx.MockTransport(fake)).ensure_zone(
        "myhost.net", ["ns1.myhost.net"], {}
    )
    assert [m for m, _, _ in fake.requests] == ["GET", "PATCH"]


def test_demo_ns_errors() -> None:
    with pytest.raises(DemoNsError, match="500"):
        DemoNs(
            ["http://ns1:8081"], "k", transport=httpx.MockTransport(FakeDemoApi(fail=True))
        ).ensure_zone("myhost.net", ["ns1.myhost.net"], {})

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(DemoNsError, match="unreachable"):
        DemoNs(["http://ns1:8081"], "k", transport=httpx.MockTransport(unreachable)).ensure_zone(
            "myhost.net", ["ns1.myhost.net"], {}
        )


@pytest.fixture
def registrar_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)
    for key, value in {
        "API_KEY": "k",
        "PDNS_API_KEY": "p",
        "DATA_DIR": str(tmp_path / "data"),
        "CONFIG_DIR": str(CONFIG),
        "DEMO_NS_API_URLS": "",
    }.items():
        monkeypatch.setenv(key, value)
    return tmp_path


def test_cli_seed_provider(registrar_env: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["seed", "provider", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {
        "name": "myhost.net",
        "nameservers": ["ns1.myhost.net", "ns2.myhost.net"],
    }
    again = runner.invoke(app, ["seed", "provider", "--ns1-ip", "192.168.1.176"])
    assert again.exit_code == 0
    assert "myhost.net: ns1.myhost.net, ns2.myhost.net" in again.output


def test_cli_seed_provider_errors(registrar_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["seed", "provider", "--domain", "github.com"])
    assert result.exit_code == 1
    assert "RESERVED_NAME" in result.output
    monkeypatch.setenv("DEMO_NS_API_URLS", "http://127.0.0.1:1")
    result = runner.invoke(app, ["seed", "provider"])
    assert result.exit_code == 1
    assert "DEMO_NS_ERROR" in result.output
