"""``plot scenario list | describe <id> | run <id|--all>`` (SPEC §9, §10).

Scenarios need the API, the resolver, the registry view and the demo-ns APIs; inside the
registrar container all of them are configured: ``docker compose exec registrar plot
scenario run --all``.
"""

import json
import os
from collections.abc import Callable
from typing import Annotated, Any

import typer

from plot.cli import output
from plot.cli.client import ApiClient
from plot.cli.output import JsonOption
from plot.dns.demo_ns import DemoNs
from plot.scenarios.engine import DEFAULT_VARIABLES, Engine, ScenarioResult, load_catalog
from plot.scenarios.live import LiveScenarioDns
from plot.verifier.dns_probe import LiveDns

app = typer.Typer(
    help="Run the scenario catalog against the sandbox (SPEC §10).", no_args_is_help=True
)

ENV_VARIABLES = {
    "lame_ip": "PLOT_LAME_IP",
    "demo_ns1_ip": "PLOT_DEMO_NS1_IP",
    "demo_ns2_ip": "PLOT_DEMO_NS2_IP",
}


def engine_from_env(api: ApiClient | None = None) -> Engine:
    probe = LiveDns.from_env()
    urls = [u.strip() for u in os.environ.get("DEMO_NS_API_URLS", "").split(",") if u.strip()]
    key = os.environ.get("PDNS_API_KEY", "")
    zones = DemoNs(urls, key) if urls and key else None
    variables = {
        name: os.environ.get(env, DEFAULT_VARIABLES[name]) for name, env in ENV_VARIABLES.items()
    }
    return Engine(
        output.client_factory(), probe, LiveScenarioDns(probe), zones, variables=variables
    )


# Replaced in tests.
engine_factory: Callable[[], Engine] = engine_from_env


@app.command("list")
def list_scenarios(as_json: JsonOption = False) -> None:
    """List the scenarios."""
    catalog = load_catalog()
    items = [{"id": s.id, "name": s.name} for s in catalog.values()]
    if as_json:
        typer.echo(json.dumps({"items": items}))
    else:
        typer.echo("\n".join(f"{i['id']}  {i['name']}" for i in items))


@app.command()
def describe(
    scenario_id: Annotated[str, typer.Argument(metavar="ID", help="Scenario id, e.g. S01.")],
    as_json: JsonOption = False,
) -> None:
    """Show what a scenario does, step by step."""
    scenario = _find(scenario_id)
    if as_json:
        typer.echo(json.dumps(scenario.model_dump(by_alias=True, exclude_none=True)))
        return
    typer.echo(f"{scenario.id}  {scenario.name}\n{scenario.description.strip()}")
    for index, step in enumerate(scenario.steps, start=1):
        what = step.title or _summary(step.model_dump(exclude_none=True))
        typer.echo(f"  {index:2d}. {step.kind:<13} {what}")


@app.command()
def run(
    scenario_id: Annotated[str | None, typer.Argument(metavar="ID", help="Scenario id.")] = None,
    run_all: Annotated[bool, typer.Option("--all", help="Run every scenario.")] = False,
    as_json: JsonOption = False,
) -> None:
    """Run one scenario or all of them; exits 1 when any scenario fails."""
    if (scenario_id is None) == (not run_all):
        raise typer.BadParameter("give a scenario ID or --all")
    catalog = load_catalog()
    scenarios = list(catalog.values()) if run_all else [_find(scenario_id or "")]
    engine = engine_factory()
    results = []
    for scenario in scenarios:
        result = engine.run(scenario)
        results.append(result)
        if not as_json:
            typer.echo(_render(result))
    if as_json:
        typer.echo(json.dumps({"results": [_as_dict(r) for r in results]}, indent=2))
    else:
        passed = sum(r.passed for r in results)
        typer.echo(f"{passed}/{len(results)} scenarios passed")
    if not all(r.passed for r in results):
        raise typer.Exit(1)


def _find(scenario_id: str) -> Any:
    catalog = load_catalog()
    scenario = catalog.get(scenario_id.upper())
    if scenario is None:
        raise typer.BadParameter(f"unknown scenario {scenario_id!r}; try `plot scenario list`")
    return scenario


def _summary(step: dict[str, Any]) -> str:
    step.pop("title", None)
    return json.dumps(step, separators=(",", ":"))[:90]


def _render(result: ScenarioResult) -> str:
    lines = [
        f"{result.id} {'PASS' if result.passed else 'FAIL'} ({result.seconds:.1f}s) {result.name}"
    ]
    for step in result.steps:
        if not step.ok or not result.passed:
            lines.append(
                f"    {step.index:2d}. {'ok  ' if step.ok else 'FAIL'} {step.title}: {step.detail}"
            )
    if result.cleanup_error:
        lines.append(f"    cleanup: {result.cleanup_error}")
    return "\n".join(lines)


def _as_dict(result: ScenarioResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "name": result.name,
        "passed": result.passed,
        "seconds": round(result.seconds, 2),
        "cleanup_error": result.cleanup_error,
        "steps": [vars(s) for s in result.steps],
    }
