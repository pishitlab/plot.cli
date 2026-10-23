"""SPEC §16 P5: `plot scenario run --all` passes on the compose stack (needs Docker)."""

import json

import pytest

from tests.integration.conftest import Stack

pytestmark = pytest.mark.integration


def test_scenario_catalog_passes_on_stack(stack: Stack) -> None:
    run = stack.compose(
        "exec", "-T", "registrar", "plot", "scenario", "run", "--all", "--json", check=False
    )
    results = {r["id"]: r for r in json.loads(run.stdout)["results"]}
    failed = {
        sid: [s["detail"] for s in r["steps"] if not s["ok"]]
        for sid, r in results.items()
        if not r["passed"]
    }
    assert failed == {}
    assert run.returncode == 0
    assert sorted(results) == [f"S{n:02d}" for n in range(1, 17)]
    assert all(r["cleanup_error"] is None for r in results.values())


def test_s06_delay_measured_within_3_seconds(stack: Stack) -> None:
    run = stack.compose("exec", "-T", "registrar", "plot", "scenario", "run", "S06", "--json")
    (result,) = json.loads(run.stdout)["results"]
    verified = [s for s in result["steps"] if s["kind"] == "verify"][-1]
    seconds = float(verified["detail"].removeprefix("VERIFIED after ").removesuffix("s"))
    assert 17 <= seconds <= 23
