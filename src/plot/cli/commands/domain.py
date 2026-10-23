"""``plot domain ...`` (SPEC §9)."""

from typing import Annotated, Any

import typer

from plot.cli.output import JsonOption, api, emit, render_domain

app = typer.Typer(help="Register and manage domains.", no_args_is_help=True)

HOLD_STATUS = "serverHold"  # `hold` is a registry hold, as in scenario S09
DEFAULT_OWNER = "cli"

Name = Annotated[str, typer.Argument(help="Domain name, e.g. shop.com.")]


@app.command()
def check(name: Name, as_json: JsonOption = False) -> None:
    """Is the name available for registration?"""
    with api() as client:
        result = client.get("/domains/check", name=name)
    emit(
        result,
        as_json,
        lambda r: (
            f"{r['name']}: {'available' if r['available'] else 'unavailable (' + r['reason'] + ')'}"
        ),
    )


@app.command()
def register(
    name: Name,
    years: Annotated[int | None, typer.Option(help="Registration period, 1-10.")] = None,
    owner: Annotated[str, typer.Option(help="Owner label.")] = DEFAULT_OWNER,
    ns: Annotated[
        list[str] | None, typer.Option("--ns", help="Nameserver; repeat for each.")
    ] = None,
    as_json: JsonOption = False,
) -> None:
    """Register a domain, optionally with its nameservers."""
    body: dict[str, Any] = {"name": name, "owner": owner, "nameservers": ns or []}
    if years is not None:
        body["years"] = years
    with api() as client:
        domain = client.post("/domains", body)
    emit(domain, as_json, render_domain)


@app.command()
def info(name: Name, as_json: JsonOption = False) -> None:
    """Show a domain: registry data and what DNS currently shows."""
    with api() as client:
        domain = client.get(f"/domains/{name}")
    emit(domain, as_json, render_domain)


@app.command("list")
def list_domains(
    prefix: Annotated[str | None, typer.Option(help="Only names starting with this.")] = None,
    owner: Annotated[str | None, typer.Option(help="Only this owner's domains.")] = None,
    as_json: JsonOption = False,
) -> None:
    """List domains (all pages)."""
    items: list[dict[str, Any]] = []
    cursor = None
    with api() as client:
        while True:
            page = client.get("/domains", prefix=prefix, owner=owner, cursor=cursor, limit=200)
            items += page["items"]
            cursor = page["next_cursor"]
            if cursor is None:
                break
    emit({"items": items}, as_json, _render_list)


def _render_list(result: dict[str, Any]) -> str:
    lines = [
        f"{d['name']}  {d['owner']}  expires {d['expires_at']}"
        f"  ns: {', '.join(d['nameservers']) or '-'}"
        for d in result["items"]
    ]
    return "\n".join(lines) or "no domains"


@app.command()
def renew(
    name: Name,
    years: Annotated[int, typer.Option(help="Years to add, 1-10.")],
    as_json: JsonOption = False,
) -> None:
    """Extend the registration."""
    with api() as client:
        domain = client.post(f"/domains/{name}/renew", {"years": years})
    emit(domain, as_json, render_domain)


@app.command()
def delete(name: Name, as_json: JsonOption = False) -> None:
    """Delete a domain and its child nameservers; the name is free at once."""
    with api() as client:
        client.delete(f"/domains/{name}")
    emit({"deleted": name}, as_json, lambda r: f"deleted {r['deleted']}")


@app.command()
def hold(name: Name, as_json: JsonOption = False) -> None:
    """Put the domain on serverHold: its delegation disappears from DNS."""
    with api() as client:
        domain = client.put(f"/domains/{name}/status", {"add": [HOLD_STATUS]})
    emit(domain, as_json, render_domain)


@app.command()
def release(name: Name, as_json: JsonOption = False) -> None:
    """Remove serverHold."""
    with api() as client:
        domain = client.put(f"/domains/{name}/status", {"remove": [HOLD_STATUS]})
    emit(domain, as_json, render_domain)


@app.command("expire-now")
def expire_now(name: Name, as_json: JsonOption = False) -> None:
    """Testing aid: move the expiry date into the past."""
    with api() as client:
        domain = client.post(f"/admin/domains/{name}/expire-now")
    emit(domain, as_json, render_domain)
