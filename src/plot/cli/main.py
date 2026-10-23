"""``plot`` command line (SPEC §9)."""

import typer

from plot.cli.commands import seed

app = typer.Typer(
    help="Domain Sandbox: registrar, registry and resolver for testing NS verification.",
    no_args_is_help=True,
)
app.add_typer(seed.app, name="seed")
