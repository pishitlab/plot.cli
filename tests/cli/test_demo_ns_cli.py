import json
from typing import Any

import pytest

from plot.cli.commands import demo_ns as demo_ns_cmd
from plot.dns.demo_ns import DemoNsError
from tests.cli.conftest import Plot


class RecordingDemoNs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str], dict[str, str]]] = []

    def ensure_zone(
        self, zone: str, nameservers: list[str], records: dict[str, str], on: Any = None
    ) -> None:
        self.calls.append((zone, nameservers, records))


@pytest.fixture
def demo(monkeypatch: pytest.MonkeyPatch) -> RecordingDemoNs:
    fake = RecordingDemoNs()
    monkeypatch.setattr(demo_ns_cmd, "demo_ns_from_env", lambda: fake)
    return fake


def test_add_zone_with_and_without_address(plot: Plot, demo: RecordingDemoNs) -> None:
    result = plot("demo-ns", "add-zone", "Shop.COM.", "--a", "10.0.16.1")
    assert (result.exit_code, result.output) == (
        0,
        "shop.com: served by ns1.myhost.net, ns2.myhost.net, www -> 10.0.16.1\n",
    )
    assert demo.calls[0] == (
        "shop.com",
        ["ns1.myhost.net", "ns2.myhost.net"],
        {"shop.com": "10.0.16.1", "www.shop.com": "10.0.16.1"},
    )
    body = json.loads(plot("demo-ns", "add-zone", "blog.com", "--json").output)
    assert body == {
        "zone": "blog.com",
        "nameservers": ["ns1.myhost.net", "ns2.myhost.net"],
        "a": None,
    }
    assert demo.calls[1][2] == {}


def test_add_zone_errors(
    plot: Plot, demo: RecordingDemoNs, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = plot("demo-ns", "add-zone", "bad_name.com")
    assert result.exit_code == 1 and result.output.startswith("INVALID_NAME: ")

    def broken() -> Any:
        raise DemoNsError("DEMO_NS_API_URLS is not set")

    monkeypatch.setattr(demo_ns_cmd, "demo_ns_from_env", broken)
    result = plot("demo-ns", "add-zone", "shop.com")
    assert (result.exit_code, result.output) == (1, "DEMO_NS_ERROR: DEMO_NS_API_URLS is not set\n")
    assert plot("demo-ns", "add-zone").exit_code == 2


def test_demo_ns_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Any) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("API_KEY", "k")
    monkeypatch.setenv("PDNS_API_KEY", "p")
    monkeypatch.setenv("DEMO_NS_API_URLS", "http://demo-ns1:8081, http://demo-ns2:8081")
    assert sorted(demo_ns_cmd.demo_ns_from_env().clients) == ["demo-ns1", "demo-ns2"]
    monkeypatch.setenv("DEMO_NS_API_URLS", "")
    with pytest.raises(DemoNsError):
        demo_ns_cmd.demo_ns_from_env()
