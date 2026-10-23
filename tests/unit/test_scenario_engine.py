from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from plot.api.app import create_app
from plot.api.deps import AppState
from plot.cli.client import ApiClient
from plot.scenarios.engine import (
    DnsAnswer,
    Engine,
    Scenario,
    ScenarioError,
    load_catalog,
    load_scenario,
)
from tests.api.conftest import API_KEY, sessions, state  # noqa: F401  (fixtures)
from tests.unit.test_verify import FakeDns, healthy

NS = ["ns1.myhost.net", "ns2.myhost.net"]


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


class ScriptedDns:
    def __init__(self) -> None:
        self.answers: dict[tuple[str, str, str], DnsAnswer] = {}
        self.asked: list[tuple[str, str, str]] = []

    def ask(self, server: str, name: str, rtype: str) -> DnsAnswer:
        self.asked.append((server, name, rtype))
        return self.answers.get((server, name, rtype), DnsAnswer("NXDOMAIN", [], []))


class FakeZones:
    def __init__(self) -> None:
        self.zones: dict[str, dict[str, Any]] = {}
        self.deleted: list[str] = []

    def ensure_zone(
        self,
        zone: str,
        nameservers: list[str],
        a_records: dict[str, str],
        on: list[str] | None = None,
    ) -> None:
        self.zones[zone] = {"ns": nameservers, "a": a_records, "on": on}

    def delete_zone(self, zone: str) -> None:
        self.deleted.append(zone)


@pytest.fixture
def api(state: AppState) -> Iterator[ApiClient]:  # noqa: F811
    with TestClient(create_app(state), headers={"X-API-Key": API_KEY}) as client:
        yield ApiClient(client)


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def verifier_dns() -> FakeDns:
    return healthy(set(NS))


@pytest.fixture
def engine(api: ApiClient, verifier_dns: FakeDns, clock: Clock) -> Engine:
    return Engine(
        api, verifier_dns, ScriptedDns(), FakeZones(), monotonic=clock.monotonic, sleep=clock.sleep
    )


def scenario(steps: list[dict[str, Any]], domains: list[str] | None = None) -> Scenario:
    return Scenario.model_validate(
        {
            "id": "T01",
            "name": "test",
            "description": "d",
            "domains": domains or ["a"],
            "steps": steps,
        }
    )


def test_happy_run_expands_names_and_cleans_up(engine: Engine, api: ApiClient) -> None:
    result = engine.run(
        scenario(
            [
                {"provider_zone": {"domain": "${a}", "records": {"www": "10.0.0.1"}}},
                {
                    "api": {
                        "method": "post",
                        "path": "/domains",
                        "body": {"name": "${a:upper}.", "owner": "s"},
                    },
                    "expect": {"status": 201, "json": {"owner": "s"}},
                },
                {
                    "api": {
                        "method": "PUT",
                        "path": "/domains/${a}/nameservers",
                        "body": {"nameservers": NS},
                    }
                },
                {"verify": {"domain": "${a}", "expect": NS, "status": "VERIFIED"}},
            ]
        )
    )
    assert result.passed, result.steps
    assert [s.kind for s in result.steps] == ["provider_zone", "api", "api", "verify"]
    assert result.steps[1].detail == "POST /domains -> 201"
    zones = engine.zones
    assert isinstance(zones, FakeZones)
    (name,) = zones.zones
    assert name.startswith("scn-t01-a-") and name.endswith(".com")
    assert zones.zones[name]["a"] == {f"www.{name}": "10.0.0.1"}
    assert zones.deleted == [name]
    assert api.get("/domains")["items"] == []  # reset scn-
    assert result.cleanup_error is None


def test_failing_step_stops_run_and_reports(engine: Engine) -> None:
    result = engine.run(
        scenario(
            [
                {"api": {"method": "GET", "path": "/domains/${a}"}, "expect": {"status": 200}},
                {"mark": "never reached"},
            ]
        )
    )
    assert not result.passed
    assert len(result.steps) == 1
    assert result.steps[0].detail == "expected HTTP 200, got 404 (DOMAIN_NOT_FOUND)"


@pytest.mark.parametrize(
    ("expect", "message"),
    [
        ({"code": "DOMAIN_EXISTS"}, "expected error DOMAIN_EXISTS, got HTTP 201"),
        ({"json": {"owner": "nobody"}}, "response owner = 's', expected 'nobody'"),
        ({"json": {"missing": 1}}, "response missing missing"),
        ({"json": {"overrides": {"ns_ttl": 5}}}, "response overrides.ns_ttl = None, expected 5"),
        ({"json": {"status": {"x": 1}}}, "response status. is not an object"),
    ],
)
def test_api_expectation_failures(engine: Engine, expect: dict[str, Any], message: str) -> None:
    result = engine.run(
        scenario(
            [
                {
                    "api": {
                        "method": "POST",
                        "path": "/domains",
                        "body": {"name": "${a}", "owner": "s"},
                    },
                    "expect": expect,
                }
            ]
        )
    )
    assert not result.passed and result.steps[0].detail == message


def test_unexpected_api_error_fails(engine: Engine) -> None:
    result = engine.run(scenario([{"api": {"method": "GET", "path": "/hosts/ns9.x.net"}}]))
    assert result.steps[0].detail == "unexpected HTTP 404 HOST_NOT_FOUND"


def test_expected_error_code_passes(engine: Engine) -> None:
    body = {"name": "${a}", "owner": "s"}
    result = engine.run(
        scenario(
            [
                {"api": {"method": "POST", "path": "/domains", "body": body}},
                {
                    "api": {"method": "POST", "path": "/domains", "body": body},
                    "expect": {"status": 409, "code": "DOMAIN_EXISTS"},
                },
            ]
        )
    )
    assert result.passed
    assert result.steps[1].detail == "POST /domains -> 409 DOMAIN_EXISTS"


def test_verify_polls_within_and_checks_elapsed(
    engine: Engine, verifier_dns: FakeDns, clock: Clock
) -> None:
    verifier_dns.parent = set()  # not delegated yet
    real = verifier_dns.registry_ns

    def delegate_after_20s(domain: str) -> Any:
        if clock.now >= 20:
            verifier_dns.parent = set(NS)
        return real(domain)

    verifier_dns.registry_ns = delegate_after_20s  # type: ignore[method-assign]
    ok = engine.run(
        scenario(
            [
                {"mark": "ns set"},
                {
                    "verify": {
                        "domain": "${a}",
                        "expect": NS,
                        "status": "VERIFIED",
                        "within": 30,
                        "elapsed": {"min": 17, "max": 23},
                    }
                },
            ]
        )
    )
    assert ok.passed, ok.steps
    assert ok.steps[1].detail == "VERIFIED after 20.0s"


def test_verify_timeout_and_elapsed_violation(
    engine: Engine, verifier_dns: FakeDns, clock: Clock
) -> None:
    verifier_dns.parent = set()
    result = engine.run(
        scenario([{"verify": {"domain": "${a}", "expect": NS, "status": "VERIFIED", "within": 5}}])
    )
    assert result.steps[0].detail == "verifier said NOT_DELEGATED, expected VERIFIED (within 5.0s)"
    assert clock.now >= 5
    verifier_dns.parent = set(NS)
    late = engine.run(
        scenario(
            [
                {
                    "verify": {
                        "domain": "${a}",
                        "expect": NS,
                        "status": "VERIFIED",
                        "elapsed": {"min": 10},
                    }
                }
            ]
        )
    )
    assert late.steps[0].detail.startswith("VERIFIED after ")
    assert late.steps[0].detail.endswith("expected 10.0-infs")


def test_dns_step(engine: Engine) -> None:
    dns = engine.dns
    assert isinstance(dns, ScriptedDns)
    passed = engine.run(
        scenario([{"dns": {"name": "never.com", "type": "NS", "rcode": "NXDOMAIN"}}])
    )
    assert passed.passed
    dns.answers[("registry", "x.com", "NS")] = DnsAnswer(
        "NOERROR", ["ns1.x.com."], ["ns1.x.com. 10.0.0.1"]
    )
    ok = engine.run(
        scenario(
            [
                {
                    "dns": {
                        "server": "registry",
                        "name": "x.com",
                        "type": "NS",
                        "glue": ["ns1.x.com. 10.0.0.1"],
                        "answers": ["ns1.x.com."],
                    }
                }
            ]
        )
    )
    assert ok.passed
    failed = engine.run(
        scenario([{"dns": {"server": "registry", "name": "x.com", "type": "NS", "glue": []}}])
    )
    assert (
        failed.steps[0].detail
        == "registry x.com NS: rcode=NOERROR answers=['ns1.x.com.'] glue=['ns1.x.com. 10.0.0.1']"
    )


def test_settings_are_restored(engine: Engine, api: ApiClient) -> None:
    result = engine.run(
        scenario(
            [
                {
                    "api": {
                        "method": "PUT",
                        "path": "/admin/settings",
                        "body": {"propagation_delay": 20},
                    }
                }
            ]
        )
    )
    assert result.passed
    assert api.get("/admin/settings")["propagation_delay"] == 0


def test_zone_step_without_demo_ns(api: ApiClient, verifier_dns: FakeDns) -> None:
    engine = Engine(api, verifier_dns, ScriptedDns(), None)
    result = engine.run(scenario([{"provider_zone": {"domain": "${a}"}}]))
    assert result.steps[0].detail.startswith("demo-ns is not configured")


def test_cleanup_errors_are_reported(api: ApiClient, verifier_dns: FakeDns) -> None:
    class BrokenZones(FakeZones):
        def delete_zone(self, zone: str) -> None:
            raise RuntimeError("demo-ns down")

    engine = Engine(api, verifier_dns, ScriptedDns(), BrokenZones())
    result = engine.run(scenario([{"provider_zone": {"domain": "${a}"}}]))
    assert result.passed and result.cleanup_error == "demo-ns down"


def test_lame_ip_and_unknown_placeholder(engine: Engine) -> None:
    result = engine.run(
        scenario(
            [
                {
                    "api": {
                        "method": "POST",
                        "path": "/hosts",
                        "body": {"name": "ns1.${a}", "ipv4": ["${lame_ip}"]},
                    },
                    "expect": {"code": "HOST_ADDR_FORBIDDEN"},
                }
            ]
        )
    )
    assert result.passed  # ns1.<a> is external because <a> is not registered
    with pytest.raises(ScenarioError, match="unknown placeholder"):
        engine.run(scenario([{"mark": "${b}"}]))


@pytest.mark.parametrize(
    "steps",
    [
        [{}],
        [{"mark": "x", "verify": {"domain": "a", "expect": [], "status": "VERIFIED"}}],
        [{"mark": "x", "expect": {"status": 200}}],
        [{"bogus": 1}],
    ],
)
def test_invalid_steps_rejected(tmp_path: Path, steps: list[dict[str, Any]]) -> None:
    path = tmp_path / "bad.yml"
    path.write_text(yaml.safe_dump({"id": "X", "name": "x", "description": "x", "steps": steps}))
    with pytest.raises(ScenarioError, match=r"bad\.yml"):
        load_scenario(path)


def test_catalog_loader(tmp_path: Path) -> None:
    for name, sid in (("a.yml", "S01"), ("b.yml", "S02")):
        (tmp_path / name).write_text(
            yaml.safe_dump({"id": sid, "name": sid, "description": "d", "steps": [{"mark": "m"}]})
        )
    assert sorted(load_catalog(tmp_path)) == ["S01", "S02"]
    (tmp_path / "c.yml").write_text(
        yaml.safe_dump({"id": "S01", "name": "dup", "description": "d", "steps": [{"mark": "m"}]})
    )
    with pytest.raises(ScenarioError, match="duplicate"):
        load_catalog(tmp_path)
