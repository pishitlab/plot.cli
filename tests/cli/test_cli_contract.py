"""SPEC §16 P4 exit gate: the command tree equals SPEC §9 (without P5 commands), every
command takes --json and answers in JSON, exit codes are 0 / 1 / 2."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import typer

from plot.cli.main import app
from tests.cli.conftest import Plot

SPEC = Path(__file__).resolve().parents[2] / "docs" / "SPEC.md"
P5_COMMANDS = {"scenario", "verify", "demo-ns"}


def spec_commands() -> set[tuple[str, ...]]:
    section = (
        SPEC.read_text(encoding="utf-8").split("## 9. CLI contract", 1)[1].split("## 10", 1)[0]
    )
    block = section.split("```", 2)[1]
    word = re.compile(r"[a-z][a-z-]*")
    commands: set[tuple[str, ...]] = set()
    for line in block.strip().splitlines():
        # options in [...] may contain "|" themselves; "|" outside them separates commands
        parts = re.sub(r"\[[^\]]*\]", "", line).removeprefix("plot ").split("|")
        group = parts[0].split()[0]
        if group in P5_COMMANDS:
            continue
        for index, part in enumerate(parts):
            part = part.strip().removeprefix(f"plot {group} ")
            leading = []
            for token in part.split():
                if not word.fullmatch(token):
                    break  # placeholders and options end the command path
                leading.append(token)
            commands.add(tuple(leading) if index == 0 else (group, *leading))
    return commands


def cli_commands() -> dict[tuple[str, ...], Any]:
    root = typer.main.get_command(app)
    found: dict[tuple[str, ...], Any] = {}
    for name, command in root.commands.items():  # type: ignore[attr-defined]
        subcommands = getattr(command, "commands", None)
        if subcommands is None:
            found[(name,)] = command
        else:
            for sub, leaf in subcommands.items():
                found[(name, sub)] = leaf
    return found


def test_command_tree_matches_spec_section_9() -> None:
    expected = spec_commands()
    assert ("domain", "release") in expected and ("override",) in expected
    assert set(cli_commands()) == expected


@pytest.mark.parametrize("path", sorted(cli_commands()))
def test_every_command_has_json_option_and_help(path: tuple[str, ...]) -> None:
    command = cli_commands()[path]
    options = {opt for param in command.params for opt in getattr(param, "opts", [])}
    assert "--json" in options
    assert command.help


def test_every_command_answers_in_json(plot: Plot) -> None:
    runs = [
        ["domain", "check", "shop.com"],
        ["domain", "register", "shop.com", "--ns", "ns1.myhost.net", "--ns", "ns2.myhost.net"],
        ["domain", "info", "shop.com"],
        ["domain", "list"],
        ["domain", "renew", "shop.com", "--years", "1"],
        ["domain", "hold", "shop.com"],
        ["domain", "release", "shop.com"],
        ["domain", "expire-now", "shop.com"],
        ["ns", "set", "shop.com", "ns1.other.net", "ns2.other.net"],
        ["ns", "clear", "shop.com"],
        ["host", "create", "ns1.shop.com", "--ipv4", "192.168.1.10"],
        ["host", "update", "ns1.shop.com", "--ipv4", "192.168.1.11"],
        ["host", "info", "ns1.shop.com"],
        ["host", "list"],
        ["host", "delete", "ns1.shop.com"],
        ["override", "shop.com", "--delay", "5"],
        ["admin", "settings"],
        ["admin", "flush", "shop.com"],
        ["domain", "delete", "shop.com"],
        ["admin", "reset", "--all"],
    ]
    covered = {tuple(run[:2]) if tuple(run[:2]) in cli_commands() else (run[0],) for run in runs}
    assert covered == set(cli_commands()) - {("seed", "provider")}  # seed: tests/unit/test_seed.py
    for run in runs:
        result = plot(*run, "--json")
        assert result.exit_code == 0, (run, result.output)
        json.loads(result.output)


@pytest.mark.parametrize("args", [["domain"], ["host"], ["admin"], ["ns"], ["seed"]])
def test_groups_without_command_show_help(plot: Plot, args: list[str]) -> None:
    result = plot(*args)
    assert result.exit_code in (0, 2)  # click shows help for groups without a command
    assert "Usage:" in result.output


def test_root_help_lists_all_groups(plot: Plot) -> None:
    text = plot("--help").output
    for name in ("domain", "ns", "host", "override", "admin", "seed"):
        assert name in text
