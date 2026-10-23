import json
import logging
import sys

import pytest
from fastapi.testclient import TestClient

from plot.api.deps import AppState
from plot.api.logging import JsonFormatter, configure_json_logging, request_id_var
from tests.api.conftest import API_KEY
from tests.api.test_contract import ExplodingPublisher


def test_formatter_writes_one_json_object_per_line() -> None:
    record = logging.LogRecord("plot.x", logging.WARNING, __file__, 1, "hello %s", ("world",), None)
    token = request_id_var.set("req-9")
    try:
        line = JsonFormatter().format(record)
    finally:
        request_id_var.reset(token)
    assert "\n" not in line
    entry = json.loads(line)
    assert {k: entry[k] for k in ("level", "logger", "message", "request_id")} == {
        "level": "warning",
        "logger": "plot.x",
        "message": "hello world",
        "request_id": "req-9",
    }
    assert entry["ts"].endswith("+00:00")


def test_formatter_includes_exceptions() -> None:
    try:
        raise ValueError("boom")
    except ValueError:
        record = logging.LogRecord("plot", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    entry = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in entry["error"] and "request_id" not in entry


def test_access_log_has_request_id_and_never_the_key(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="plot.access")
    response = client.post("/api/v1/domains", json={"name": "shop.com", "owner": "a"})
    (record,) = [r for r in caplog.records if r.name == "plot.access"]
    entry = json.loads(JsonFormatter().format(record))
    assert entry["request_id"] == response.headers["X-Request-ID"]
    assert (entry["method"], entry["path"], entry["status"]) == ("POST", "/api/v1/domains", 201)
    assert entry["duration_ms"] >= 0
    assert API_KEY not in caplog.text


def test_unhandled_error_logged_with_request_id(
    client: TestClient, caplog: pytest.LogCaptureFixture, state: AppState
) -> None:
    state.publisher = ExplodingPublisher()
    caplog.set_level(logging.INFO)
    response = client.post("/api/v1/domains", json={"name": "boom.com", "owner": "a"})
    (error,) = [r for r in caplog.records if r.name == "plot.api"]
    entry = json.loads(JsonFormatter().format(error))
    assert entry["request_id"] == response.headers["X-Request-ID"]
    assert "pdns client bug" in entry["error"]


def test_configure_json_logging_replaces_text_handlers() -> None:
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    try:
        configure_json_logging()
        assert len(root.handlers) == 1 and isinstance(root.handlers[0].formatter, JsonFormatter)
        assert logging.getLogger("uvicorn.error").handlers == []
        assert logging.getLogger("uvicorn.error").propagate
        assert logging.getLogger("uvicorn.access").disabled
    finally:
        root.handlers, _ = saved
        root.setLevel(saved[1])
        logging.getLogger("uvicorn.access").disabled = False
