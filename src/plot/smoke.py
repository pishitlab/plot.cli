"""Quick check of a running stack from the outside (``make smoke``).

Usage: ``python -m plot.smoke [ENV_FILE]`` — reads BIND_ADDR and API_KEY from the env file.
"""

import secrets
import sys
from collections.abc import Callable
from pathlib import Path

import dns.exception
import dns.flags
import dns.message
import dns.query
import dns.rcode
import dns.resolver
import httpx

Check = tuple[str, Callable[[], str]]


class SmokeFailure(Exception):
    pass


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def checks(addr: str, api_key: str, timeout: float = 5.0) -> list[Check]:
    api = f"http://{addr}:8080/api/v1"
    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [addr]
    resolver.lifetime = timeout

    def health() -> str:
        body = httpx.get(f"{api}/health", timeout=timeout).json()
        if body.get("status") != "ok":
            raise SmokeFailure(f"health: {body}")
        return "db, pdns, unbound ok"

    def api_key_works() -> str:
        response = httpx.get(
            f"{api}/admin/settings", headers={"X-API-Key": api_key}, timeout=timeout
        )
        if response.status_code != 200:
            raise SmokeFailure(f"HTTP {response.status_code}")
        return "API key accepted"

    def unregistered_is_nxdomain() -> str:
        name = f"smoke-{secrets.token_hex(4)}.com"
        try:
            resolver.resolve(name, "A")
        except dns.resolver.NXDOMAIN:
            return f"{name} NXDOMAIN"
        raise SmokeFailure(f"{name} resolved")

    def passthrough() -> str:
        answer = resolver.resolve("github.com", "A")
        return f"github.com -> {answer[0].to_text()}"

    def registry_view() -> str:
        query = dns.message.make_query(".", "SOA")
        query.flags &= ~dns.flags.RD
        reply = dns.query.udp(query, addr, port=5300, timeout=timeout)
        if reply.rcode() != dns.rcode.NOERROR or not reply.answer:
            raise SmokeFailure(dns.rcode.to_text(reply.rcode()))
        return "pdns-root answers SOA ."

    def provider_seeded() -> str:
        names = sorted(r.to_text() for r in resolver.resolve("myhost.net", "NS"))
        return f"myhost.net NS {', '.join(names)}"

    return [
        ("registrar health", health),
        ("API key", api_key_works),
        ("unregistered name", unregistered_is_nxdomain),
        ("passthrough", passthrough),
        ("registry view :5300", registry_view),
        ("provider seed (plot seed provider)", provider_seeded),
    ]


def run(selected: list[Check]) -> int:
    failures = 0
    for title, check in selected:
        try:
            detail = check()
            sys.stdout.write(f"ok    {title}: {detail}\n")
        except (
            SmokeFailure,
            httpx.HTTPError,
            dns.exception.DNSException,
            OSError,
            ValueError,
        ) as err:
            failures += 1
            sys.stdout.write(f"FAIL  {title}: {type(err).__name__}: {err}\n")
    sys.stdout.write(f"{len(selected) - failures}/{len(selected)} checks passed\n")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    env = read_env(Path(argv[1] if len(argv) > 1 else ".env"))
    return run(checks(env["BIND_ADDR"], env["API_KEY"]))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
