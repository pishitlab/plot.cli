"""``plot verify <domain> --expect <ns1> <ns2> ...`` (SPEC §9, §11)."""

from collections.abc import Callable
from typing import Annotated, Any

import typer

from plot.cli import output
from plot.cli.client import ApiClient, ApiError
from plot.cli.output import JsonOption, emit
from plot.verifier.dns_probe import LiveDns
from plot.verifier.verify import DnsProbe, verify

# Replaced in tests with fake DNS.
dns_factory: Callable[[], DnsProbe] = LiveDns.from_env


def registration_lookup(client: ApiClient) -> Callable[[str], bool | None]:
    """A-025: only the registry database knows a registered name without delegation."""

    def is_registered(name: str) -> bool | None:
        try:
            check = client.get("/domains/check", name=name)
        except ApiError:
            return None
        return bool(not check["available"] and check.get("reason") == "DOMAIN_EXISTS")

    return is_registered


def verify_command(
    domain: Annotated[str, typer.Argument(help="Domain to check.")],
    nameservers: Annotated[
        list[str], typer.Argument(help="Expected nameservers (after --expect).", show_default=False)
    ],
    expect: Annotated[
        bool, typer.Option("--expect", help="The arguments after the domain are the expected NS.")
    ] = False,
    as_json: JsonOption = False,
) -> None:
    """Has DOMAIN been delegated to exactly the expected nameservers, and do they answer?"""
    if not expect:
        raise typer.BadParameter("list the expected nameservers after --expect")
    lookup = registration_lookup(output.client_factory())
    result = verify(domain, nameservers, dns_factory(), lookup)
    emit(result.to_dict(), as_json, _render)


def _render(r: dict[str, Any]) -> str:
    evidence = r["evidence"]
    registry = ", ".join(evidence["parent_ns"]) or (
        "NXDOMAIN" if evidence["registry_nxdomain"] else "-"
    )
    lines = [
        f"{r['domain']}: {r['status']}",
        f"  expected:    {', '.join(r['expected'])}",
        f"  registry:    {registry}",
        f"  resolver:    {', '.join(evidence['resolver_ns']) or '-'}",
    ]
    lines += [
        f"  probe {p['nameserver']}: {'ok' if p['ok'] else 'FAIL'} ({p['detail']})"
        for p in evidence["probes"]
    ]
    if evidence["error"]:
        lines.append(f"  error:       {evidence['error']}")
    return "\n".join(lines)
