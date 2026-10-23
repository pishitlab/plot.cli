import json

import pytest

from plot.cli.commands import verify as verify_cmd
from tests.cli.conftest import Plot
from tests.unit.test_verify import FakeDns, healthy

EXPECTED = ["ns1.myhost.net", "ns2.myhost.net"]


@pytest.fixture
def fake_dns(monkeypatch: pytest.MonkeyPatch) -> FakeDns:
    dns = healthy(set(EXPECTED))
    monkeypatch.setattr(verify_cmd, "dns_factory", lambda: dns)
    return dns


def test_verified_text_and_json(plot: Plot, fake_dns: FakeDns) -> None:
    result = plot("verify", "Shop.COM", "--expect", "ns1.myhost.net", "ns2.myhost.net")
    assert result.exit_code == 0, result.output
    assert result.output.splitlines()[:4] == [
        "shop.com: VERIFIED",
        "  expected:    ns1.myhost.net, ns2.myhost.net",
        "  registry:    ns1.myhost.net, ns2.myhost.net",
        "  resolver:    ns1.myhost.net, ns2.myhost.net",
    ]
    assert "  probe ns2.myhost.net: ok (authoritative)" in result.output
    body = json.loads(plot("verify", "shop.com", "--expect", *EXPECTED, "--json").output)
    assert body["status"] == "VERIFIED" and len(body["evidence"]["probes"]) == 2


def test_registration_lookup_separates_not_delegated_from_nxdomain(
    plot: Plot, fake_dns: FakeDns
) -> None:
    fake_dns.parent, fake_dns.nxdomain = set(), True
    assert "never.com: NXDOMAIN" in plot("verify", "never.com", "--expect", *EXPECTED).output
    plot("domain", "register", "shop.com")
    text = plot("verify", "shop.com", "--expect", *EXPECTED).output
    assert text.startswith("shop.com: NOT_DELEGATED")
    assert "registry:    NXDOMAIN" in text


def test_failures_are_explained(plot: Plot, fake_dns: FakeDns) -> None:
    fake_dns.authoritative = {"172.28.0.31"}
    text = plot("verify", "shop.com", "--expect", *EXPECTED).output
    assert "shop.com: LAME" in text
    assert "probe ns2.myhost.net: FAIL (no authoritative answer from 172.28.0.32)" in text
    fake_dns.registry_down = True
    text = plot("verify", "shop.com", "--expect", *EXPECTED).output
    assert "shop.com: ERROR" in text and "error:       registry timeout" in text


def test_usage(plot: Plot, fake_dns: FakeDns) -> None:
    assert plot("verify", "shop.com", "ns1.myhost.net").exit_code == 2  # --expect missing
    assert plot("verify", "shop.com", "--expect").exit_code == 2  # no nameservers
    assert plot("verify").exit_code == 2


def test_lookup_unknown_when_api_unreachable() -> None:
    from plot.cli.client import ApiClient, ApiError

    class Down(ApiClient):
        def __init__(self) -> None:
            pass

        def get(self, path: str, **params: object) -> object:
            raise ApiError("CONNECTION_ERROR", "down")

    assert verify_cmd.registration_lookup(Down())("shop.com") is None
