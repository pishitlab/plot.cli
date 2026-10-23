from pathlib import Path

import httpx
import pytest

from plot import smoke


def test_run_reports_each_check(capsys: pytest.CaptureFixture[str]) -> None:
    def fail() -> str:
        raise smoke.SmokeFailure("health: degraded")

    def unreachable() -> str:
        raise httpx.ConnectError("refused")

    code = smoke.run([("good", lambda: "fine"), ("bad", fail), ("down", unreachable)])
    out = capsys.readouterr().out.splitlines()
    assert code == 1
    assert out == [
        "ok    good: fine",
        "FAIL  bad: SmokeFailure: health: degraded",
        "FAIL  down: ConnectError: refused",
        "1/3 checks passed",
    ]
    assert smoke.run([("good", lambda: "fine")]) == 0


def test_checks_cover_the_stack() -> None:
    titles = [title for title, _ in smoke.checks("127.0.0.1", "k")]
    assert titles == [
        "registrar health",
        "API key",
        "unregistered name",
        "passthrough",
        "registry view :5300",
        "provider seed (plot seed provider)",
    ]


def test_against_nothing_everything_fails(capsys: pytest.CaptureFixture[str]) -> None:
    # 127.0.0.9 has no sandbox: every check must fail, none may hang past its timeout
    assert smoke.run(smoke.checks("127.0.0.9", "k", timeout=0.3)) == 1
    assert capsys.readouterr().out.endswith("0/6 checks passed\n")


def test_main_reads_env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / "it.env"
    env.write_text("# comment\nBIND_ADDR=127.0.0.9\nAPI_KEY=k\n\n")
    seen: list[tuple[str, str]] = []

    def fake_checks(addr: str, key: str) -> list[smoke.Check]:
        seen.append((addr, key))
        return []

    monkeypatch.setattr(smoke, "checks", fake_checks)
    assert smoke.main(["smoke", str(env)]) == 0
    monkeypatch.setenv("BIND_ADDR", "10.0.0.5")
    monkeypatch.setenv("API_KEY", "from-env")
    assert smoke.main(["smoke"]) == 0
    assert seen == [("127.0.0.9", "k"), ("10.0.0.5", "from-env")]
