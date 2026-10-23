"""``plot ns ...`` (SPEC §9)."""

from typing import Annotated

import typer

from plot.cli.output import JsonOption, api, emit, render_domain

app = typer.Typer(help="Set or clear a domain's nameservers.", no_args_is_help=True)


@app.command("set")
def set_nameservers(
    domain: Annotated[str, typer.Argument(help="Domain name.")],
    nameservers: Annotated[list[str], typer.Argument(help="Nameserver host names.")],
    as_json: JsonOption = False,
) -> None:
    """Replace the whole nameserver set."""
    with api() as client:
        result = client.put(f"/domains/{domain}/nameservers", {"nameservers": nameservers})
    emit(result, as_json, render_domain)


@app.command()
def clear(
    domain: Annotated[str, typer.Argument(help="Domain name.")], as_json: JsonOption = False
) -> None:
    """Remove all nameservers: the domain stays registered without delegation."""
    with api() as client:
        result = client.put(f"/domains/{domain}/nameservers", {"nameservers": []})
    emit(result, as_json, render_domain)
