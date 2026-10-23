"""``plot override`` and ``plot admin ...`` (SPEC §9)."""

from typing import Annotated, Any

import typer

from plot.cli.output import JsonOption, api, emit, render_domain

app = typer.Typer(help="Sandbox controls: settings, reset, resolver cache.", no_args_is_help=True)

NONE = "none"


def seconds_or_none(value: str) -> int | None:
    """``none`` clears an override; otherwise a non-negative number of seconds."""
    if value.lower() == NONE:
        return None
    if not value.isdigit():
        raise typer.BadParameter(f"expected seconds or '{NONE}', got {value!r}")
    return int(value)


DelayOrNone = Annotated[
    str | None, typer.Option("--delay", help="Propagation delay in seconds, or 'none'.")
]
TtlOrNone = Annotated[str | None, typer.Option("--ttl", help="NS/glue TTL in seconds, or 'none'.")]


def override(
    domain: Annotated[str, typer.Argument(help="Domain name.")],
    delay: DelayOrNone = None,
    ttl: TtlOrNone = None,
    as_json: JsonOption = False,
) -> None:
    """Per-domain propagation delay / TTL; 'none' falls back to the global setting."""
    body: dict[str, Any] = {}
    if delay is not None:
        body["propagation_delay"] = seconds_or_none(delay)
    if ttl is not None:
        body["ns_ttl"] = seconds_or_none(ttl)
    with api() as client:
        result = client.put(f"/domains/{domain}/overrides", body)
    emit(result, as_json, render_domain)


@app.command()
def settings(
    delay: Annotated[
        int | None, typer.Option("--delay", min=0, help="Global propagation delay (s).")
    ] = None,
    ttl: Annotated[int | None, typer.Option("--ttl", min=0, help="Global NS/glue TTL (s).")] = None,
    as_json: JsonOption = False,
) -> None:
    """Show the global settings, or change them when options are given."""
    changes = {
        key: value
        for key, value in (("propagation_delay", delay), ("ns_ttl", ttl))
        if value is not None
    }
    with api() as client:
        result = (
            client.put("/admin/settings", changes) if changes else client.get("/admin/settings")
        )
    emit(result, as_json, lambda r: "\n".join(f"{k}: {v}" for k, v in sorted(r.items())))


@app.command()
def reset(
    prefix: Annotated[str | None, typer.Option(help="Remove domains starting with this.")] = None,
    everything: Annotated[
        bool, typer.Option("--all", help="Remove every non-seed domain.")
    ] = False,
    as_json: JsonOption = False,
) -> None:
    """Remove test domains and hosts (seed data stays), clear their DNS, flush the resolver."""
    if (prefix is None) == (not everything):
        raise typer.BadParameter("give exactly one of --prefix or --all")
    body: dict[str, Any] = {"all": True} if everything else {"prefix": prefix}
    with api() as client:
        result = client.post("/admin/reset", body)
    emit(
        result,
        as_json,
        lambda r: f"removed {len(r['deleted_domains'])} domains, {len(r['deleted_hosts'])} hosts",
    )


@app.command()
def flush(
    domain: Annotated[str | None, typer.Argument(help="Domain; omit to flush everything.")] = None,
    as_json: JsonOption = False,
) -> None:
    """Flush the resolver cache for a domain, or entirely."""
    with api() as client:
        result = client.post("/admin/resolver/flush", {"domain": domain})
    emit(result, as_json, lambda r: f"flushed {r['flushed'] or 'everything'}")
