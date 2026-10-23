"""OpenAPI snapshot (SPEC §8.3): any change to the API contract must show up in review.

Regenerate after an approved contract change with:
    PLOT_UPDATE_SNAPSHOT=1 .venv/bin/pytest tests/api/test_openapi.py
"""

import json
import os
from pathlib import Path

from plot.api.app import create_app
from plot.api.deps import AppState

SNAPSHOT = Path(__file__).with_name("openapi.snapshot.json")


def test_openapi_matches_snapshot(state: AppState) -> None:
    current = json.dumps(create_app(state).openapi(), indent=2, sort_keys=True) + "\n"
    if os.environ.get("PLOT_UPDATE_SNAPSHOT") == "1":
        SNAPSHOT.write_text(current, encoding="utf-8")
    assert SNAPSHOT.exists(), "snapshot missing; run with PLOT_UPDATE_SNAPSHOT=1"
    assert current == SNAPSHOT.read_text(encoding="utf-8")
