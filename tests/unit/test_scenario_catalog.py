"""The shipped catalog (SPEC §10) parses, and each scenario expands with its own names."""

import re

import pytest

from plot.scenarios.engine import DEFAULT_VARIABLES, Scenario, _expand, load_catalog

CATALOG = load_catalog()
PLACEHOLDER = re.compile(r"\$\{([a-z_][a-z0-9_]*)(?::upper)?\}")


def test_ids_are_known_spec_scenarios() -> None:
    assert set(CATALOG) <= {f"S{n:02d}" for n in range(1, 17)}


@pytest.mark.parametrize("sid", sorted(CATALOG))
def test_placeholders_are_declared(sid: str) -> None:
    scenario: Scenario = CATALOG[sid]
    text = str(scenario.model_dump())
    used = set(PLACEHOLDER.findall(text))
    assert used <= set(scenario.domains) | set(DEFAULT_VARIABLES)
    names = {d: f"scn-{d}.com" for d in scenario.domains}
    expanded = _expand(
        scenario.model_dump(by_alias=True, exclude_none=True), {**DEFAULT_VARIABLES, **names}
    )
    assert "${" not in str(expanded)


def test_catalog_is_complete() -> None:
    assert sorted(CATALOG) == [f"S{n:02d}" for n in range(1, 17)]
