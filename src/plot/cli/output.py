"""Shared options and output of ``plot`` commands (SPEC §9: ``--json`` everywhere,
exit 1 with ``code: message`` on API errors, exit 2 on usage errors)."""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Annotated, Any

import typer

from plot.cli.client import ApiClient, ApiError

JsonOption = Annotated[bool, typer.Option("--json", help="Print the API response as JSON.")]

# Replaced in tests to talk to an in-process app.
client_factory: Callable[[], ApiClient] = ApiClient.from_env


@contextmanager
def api() -> Iterator[ApiClient]:
    try:
        yield client_factory()
    except ApiError as err:
        typer.echo(f"{err.code}: {err.message}", err=True)
        raise typer.Exit(1) from None


def emit(data: Any, as_json: bool, render: Callable[[Any], str]) -> None:
    if as_json:
        typer.echo(json.dumps(data, indent=2, sort_keys=True))
    else:
        typer.echo(render(data))


def render_domain(d: dict[str, Any]) -> str:
    visible = d["dns_visible"]
    pending = ", ".join(p["apply_at"] for p in visible["pending"]) or "-"
    overrides = d["overrides"]
    lines = [
        f"name:         {d['name']}",
        f"owner:        {d['owner']}",
        f"status:       {', '.join(d['status']) or '-'}{' (expired)' if d['expired'] else ''}",
        f"expires:      {d['expires_at']}",
        f"nameservers:  {', '.join(d['nameservers']) or '-'}",
        f"dns visible:  {', '.join(visible['nameservers']) or '-'}"
        f" (published {visible['published_at'] or 'never'}; pending {pending})",
        f"overrides:    delay={_none(overrides['propagation_delay'])}"
        f" ttl={_none(overrides['ns_ttl'])}",
    ]
    return "\n".join(lines)


def render_host(h: dict[str, Any]) -> str:
    addresses = ", ".join(h["ipv4"] + h["ipv6"]) or "-"
    used = ", ".join(h["used_by"]) or "-"
    parent = f" of {h['parent_domain']}" if h["parent_domain"] else ""
    return f"{h['name']}  {h['kind']}{parent}  addresses: {addresses}  used by: {used}"


def _none(value: Any) -> str:
    return "none" if value is None else str(value)
