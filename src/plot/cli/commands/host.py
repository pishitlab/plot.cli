"""``plot host ...`` (SPEC §9)."""

from typing import Annotated, Any

import typer

from plot.cli.output import JsonOption, api, emit, render_host

app = typer.Typer(help="Manage hosts (child nameservers and their glue).", no_args_is_help=True)

Name = Annotated[str, typer.Argument(help="Host name, e.g. ns1.shop.com.")]
Ipv4 = Annotated[list[str] | None, typer.Option("--ipv4", help="IPv4 address; repeat for each.")]
Ipv6 = Annotated[list[str] | None, typer.Option("--ipv6", help="IPv6 address; repeat for each.")]


@app.command()
def create(name: Name, ipv4: Ipv4 = None, ipv6: Ipv6 = None, as_json: JsonOption = False) -> None:
    """Create a host. A host under a registered domain needs an address (glue)."""
    with api() as client:
        host = client.post("/hosts", {"name": name, "ipv4": ipv4 or [], "ipv6": ipv6 or []})
    emit(host, as_json, render_host)


@app.command()
def update(name: Name, ipv4: Ipv4 = None, ipv6: Ipv6 = None, as_json: JsonOption = False) -> None:
    """Replace the addresses of the families given; the others are kept."""
    body: dict[str, Any] = {}
    if ipv4 is not None:
        body["ipv4"] = ipv4
    if ipv6 is not None:
        body["ipv6"] = ipv6
    with api() as client:
        host = client.put(f"/hosts/{name}", body)
    emit(host, as_json, render_host)


@app.command()
def delete(name: Name, as_json: JsonOption = False) -> None:
    """Delete a host that no domain uses as nameserver."""
    with api() as client:
        client.delete(f"/hosts/{name}")
    emit({"deleted": name}, as_json, lambda r: f"deleted {r['deleted']}")


@app.command()
def info(name: Name, as_json: JsonOption = False) -> None:
    """Show a host."""
    with api() as client:
        host = client.get(f"/hosts/{name}")
    emit(host, as_json, render_host)


@app.command("list")
def list_hosts(as_json: JsonOption = False) -> None:
    """List hosts."""
    with api() as client:
        result = client.get("/hosts")
    emit(result, as_json, lambda r: "\n".join(render_host(h) for h in r["items"]) or "no hosts")
