"""``plot seed``: the one command that works on the database instead of the API."""

import json
from typing import Annotated

import typer

from plot.cli.output import JsonOption
from plot.core.errors import PlotError
from plot.core.settings import load_env_config
from plot.dns.demo_ns import DemoNs, DemoNsError
from plot.services.context import ServiceContext
from plot.services.events import RequestContext
from plot.services.seed import seed_provider
from plot.services.settings import load_settings

app = typer.Typer(help="Seed data that runs inside the registrar container (direct DB access).")

CLI_ACTOR = "cli"


@app.command("provider")
def seed_provider_command(
    domain: Annotated[str, typer.Option(help="Provider domain to register.")] = "myhost.net",
    ns1_ip: Annotated[str, typer.Option(help="Address of ns1.<domain>.")] = "172.28.0.31",
    ns2_ip: Annotated[str, typer.Option(help="Address of ns2.<domain>.")] = "172.28.0.32",
    as_json: JsonOption = False,
) -> None:
    """Register the provider domain with glue (seed, kept by reset) and serve its zone on
    demo-ns. Needs direct access to the registrar database: run it in the registrar
    container (``docker compose exec registrar plot seed provider``)."""
    from plot.api.main import build  # composition root: only this command needs it

    config = load_env_config()
    state, _ = build(config)
    try:
        with state.sessions.begin() as session:
            ctx = ServiceContext(
                session=session,
                clock=state.clock,
                publisher=state.publisher,
                policy=state.policy,
                settings=load_settings(session, state.settings_defaults),
                request=RequestContext(actor=CLI_ACTOR, request_id="seed-provider"),
            )
            view = seed_provider(ctx, domain, [ns1_ip, ns2_ip])
        urls = [u.strip() for u in config.demo_ns_api_urls.split(",") if u.strip()]
        if urls:
            DemoNs(urls, config.pdns_api_key.get_secret_value()).ensure_zone(
                view.name,
                view.nameservers,
                dict(zip(view.nameservers, [ns1_ip, ns2_ip], strict=True)),
            )
    except PlotError as err:
        typer.echo(f"{err.code}: {err.message}", err=True)
        raise typer.Exit(1) from None
    except DemoNsError as err:
        typer.echo(f"DEMO_NS_ERROR: {err}", err=True)
        raise typer.Exit(1) from None
    if as_json:
        typer.echo(json.dumps({"name": view.name, "nameservers": view.nameservers}))
    else:
        typer.echo(f"{view.name}: {', '.join(view.nameservers)} (demo-ns zones: {len(urls)})")
