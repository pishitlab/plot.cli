"""``plot`` command line (SPEC §9)."""

import typer

from plot.cli.commands import admin, demo_ns, domain, host, ns, scenario, seed, verify

app = typer.Typer(
    help="Domain Sandbox: registrar, registry and resolver for testing NS verification.",
    no_args_is_help=True,
)
app.add_typer(domain.app, name="domain")
app.add_typer(ns.app, name="ns")
app.add_typer(host.app, name="host")
app.command("override")(admin.override)
app.add_typer(admin.app, name="admin")
app.add_typer(seed.app, name="seed")
app.command("verify")(verify.verify_command)
app.add_typer(demo_ns.app, name="demo-ns")
app.add_typer(scenario.app, name="scenario")
