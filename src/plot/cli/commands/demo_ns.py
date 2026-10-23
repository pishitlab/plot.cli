"""``plot demo-ns add-zone``: serve a customer zone on the stand-in provider (SPEC §9, D-012).

Talks to the demo-ns pdns APIs, which only exist inside the compose network: run it in the
registrar container (``docker compose exec registrar plot demo-ns add-zone ...``).
"""

import json
from typing import Annotated

import typer

from plot.cli.output import JsonOption
from plot.core.errors import PlotError
from plot.core.names import normalize_name
from plot.core.settings import load_env_config
from plot.dns.demo_ns import DemoNs, DemoNsError

app = typer.Typer(help="Zones on the demo provider nameservers (run in the registrar container).")

PROVIDER_NS = ["ns1.myhost.net", "ns2.myhost.net"]


def demo_ns_from_env() -> DemoNs:
    config = load_env_config()
    urls = [u.strip() for u in config.demo_ns_api_urls.split(",") if u.strip()]
    if not urls:
        raise DemoNsError("DEMO_NS_API_URLS is not set")
    return DemoNs(urls, config.pdns_api_key.get_secret_value())


@app.command("add-zone")
def add_zone(
    domain: Annotated[str, typer.Argument(help="Customer domain to serve.")],
    a: Annotated[str | None, typer.Option("--a", help="Address for the apex and www.")] = None,
    as_json: JsonOption = False,
) -> None:
    """Serve DOMAIN on demo-ns1/2 with NS ns1/ns2.myhost.net (and A records with --a)."""
    try:
        name = normalize_name(domain)
        records = {name: a, f"www.{name}": a} if a else {}
        demo_ns_from_env().ensure_zone(name, PROVIDER_NS, records)
    except PlotError as err:
        typer.echo(f"{err.code}: {err.message}", err=True)
        raise typer.Exit(1) from None
    except DemoNsError as err:
        typer.echo(f"DEMO_NS_ERROR: {err}", err=True)
        raise typer.Exit(1) from None
    result = {"zone": name, "nameservers": PROVIDER_NS, "a": a}
    if as_json:
        typer.echo(json.dumps(result))
    else:
        typer.echo(f"{name}: served by {', '.join(PROVIDER_NS)}" + (f", www -> {a}" if a else ""))
