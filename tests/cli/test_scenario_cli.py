import json

import pytest

from plot.cli.commands import scenario as scenario_cmd
from plot.scenarios.engine import Engine, ScenarioResult, StepResult
from tests.cli.conftest import Plot


class FakeEngine(Engine):
    def __init__(self, failing: set[str] | None = None) -> None:
        self.failing = failing or set()
        self.ran: list[str] = []

    def run(self, scenario: object) -> ScenarioResult:
        sid = scenario.id  # type: ignore[attr-defined]
        self.ran.append(sid)
        ok = sid not in self.failing
        step = StepResult(
            1,
            "verify",
            "verifier",
            ok,
            "VERIFIED after 1.0s" if ok else "verifier said MISMATCH",
            1.0,
        )
        return ScenarioResult(sid, scenario.name, ok, [step], 1.5)  # type: ignore[attr-defined]


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> FakeEngine:
    fake = FakeEngine()
    monkeypatch.setattr(scenario_cmd, "engine_factory", lambda: fake)
    return fake


def test_list(plot: Plot) -> None:
    lines = plot("scenario", "list").output.splitlines()
    assert len(lines) == 16
    assert lines[0] == "S01  happy path (external NS)"
    items = json.loads(plot("scenario", "list", "--json").output)["items"]
    assert [i["id"] for i in items][-1] == "S16"


def test_describe(plot: Plot) -> None:
    text = plot("scenario", "describe", "s06").output
    assert text.startswith("S06  propagation delay\n")
    assert " 4. mark " in text
    assert "about 20 s later it is verified" in text
    body = json.loads(plot("scenario", "describe", "S01", "--json").output)
    assert body["id"] == "S01" and body["steps"][0]["provider_zone"]["domain"] == "${a}"
    assert plot("scenario", "describe", "S99").exit_code == 2


def test_run_one_and_all(plot: Plot, engine: FakeEngine) -> None:
    result = plot("scenario", "run", "S01")
    assert (result.exit_code, result.output) == (
        0,
        "S01 PASS (1.5s) happy path (external NS)\n1/1 scenarios passed\n",
    )
    result = plot("scenario", "run", "--all", "--json")
    assert result.exit_code == 0
    body = json.loads(result.output)
    assert [r["id"] for r in body["results"]] == [f"S{n:02d}" for n in range(1, 17)]
    assert body["results"][0]["steps"][0]["detail"] == "VERIFIED after 1.0s"


def test_failures_exit_1_with_details(plot: Plot, engine: FakeEngine) -> None:
    engine.failing = {"S07"}
    result = plot("scenario", "run", "--all")
    assert result.exit_code == 1
    assert "S07 FAIL (1.5s) moved away after verification" in result.output
    assert "     1. FAIL verifier: verifier said MISMATCH" in result.output
    assert result.output.endswith("15/16 scenarios passed\n")


def test_run_usage(plot: Plot, engine: FakeEngine) -> None:
    assert plot("scenario", "run").exit_code == 2
    assert plot("scenario", "run", "S01", "--all").exit_code == 2
    assert plot("scenario", "run", "S99").exit_code == 2
    assert engine.ran == []


def test_engine_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLOT_RESOLVER", "172.28.0.2")
    monkeypatch.setenv("PLOT_REGISTRY_ADDR", "172.28.0.10:53")
    monkeypatch.setenv("DEMO_NS_API_URLS", "http://demo-ns1:8081")
    monkeypatch.setenv("PDNS_API_KEY", "k")
    monkeypatch.setenv("PLOT_LAME_IP", "10.9.9.9")
    engine = scenario_cmd.engine_from_env()
    assert engine.zones is not None
    assert engine.variables["lame_ip"] == "10.9.9.9"
    monkeypatch.delenv("PDNS_API_KEY")
    assert scenario_cmd.engine_from_env().zones is None
