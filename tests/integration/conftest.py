"""Integration fixtures: talk to a running stack (`make up`) through BIND_ADDR.

Configuration comes from the env file named by PLOT_ENV_FILE (default ``.env``), the same
file `make up` used. Docker access goes through ``docker compose`` with that file.
"""

import os
import secrets
import subprocess
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dns.flags
import dns.message
import dns.query
import dns.rcode
import dns.resolver
import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
POLL_TIMEOUT = 30.0  # SPEC §14: polling with a timeout of at most 30 seconds


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


@dataclass
class Stack:
    env_file: Path
    env: dict[str, str]

    @property
    def addr(self) -> str:
        return self.env["BIND_ADDR"]

    def compose(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = [
            "docker", "compose", "--env-file", str(self.env_file), "--project-directory",
            str(ROOT), "-f", str(ROOT / "deploy" / "docker-compose.yml"), *args,
        ]  # fmt: skip
        return subprocess.run(cmd, check=check, capture_output=True, text=True, timeout=120)

    def container(self, service: str) -> str:
        return self.compose("ps", "-q", service).stdout.strip()

    def exec(self, service: str, *args: str) -> str:
        return self.compose("exec", "-T", service, *args).stdout

    def api(self) -> httpx.Client:
        return httpx.Client(
            base_url=f"http://{self.addr}:8080/api/v1",
            headers={"X-API-Key": self.env["API_KEY"]},
            timeout=10,
        )

    def resolver(self) -> dns.resolver.Resolver:
        res = dns.resolver.Resolver(configure=False)
        res.nameservers = [self.addr]
        res.lifetime = 5
        res.cache = None
        return res

    def resolve(self, name: str, rtype: str) -> list[str]:
        try:
            answer = self.resolver().resolve(name, rtype)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return []
        return sorted(r.to_text() for r in answer)

    def rcode(self, name: str, rtype: str) -> str:
        query = dns.message.make_query(name, rtype)
        return dns.rcode.to_text(dns.query.udp(query, self.addr, timeout=5).rcode())

    def registry(self, name: str) -> dns.message.Message:
        """Registry view: ask pdns-root directly without recursion (SPEC §7.3)."""
        query = dns.message.make_query(name, "NS")
        query.flags &= ~dns.flags.RD
        return dns.query.udp(query, self.addr, port=5300, timeout=5)

    def unbound_option(self, option: str) -> str:
        return self.exec(
            "unbound", "unbound-control", "-c", "/etc/unbound/unbound.conf",
            "-s", "127.0.0.1@8953", "get_option", option,
        ).strip()  # fmt: skip

    def provider_zone(self, service: str, zone: str, records: dict[str, str]) -> None:
        """Serve ``zone`` on a demo-ns with apex NS ns1/ns2.myhost.net and A records."""
        self.exec(service, "pdnsutil", "create-zone", zone, "ns1.myhost.net")
        self.exec(service, "pdnsutil", "add-record", zone, "@", "NS", "60", "ns2.myhost.net")
        for label, address in records.items():
            self.exec(service, "pdnsutil", "add-record", zone, label, "A", "60", address)

    def drop_zone(self, service: str, zone: str) -> None:
        self.compose("exec", "-T", service, "pdnsutil", "delete-zone", zone, check=False)


def wait_for[T](
    probe: Callable[[], T], until: Callable[[T], bool], timeout: float = POLL_TIMEOUT
) -> T:
    deadline = time.monotonic() + timeout
    while True:
        value = probe()
        if until(value):
            return value
        if time.monotonic() > deadline:
            raise AssertionError(f"timed out after {timeout}s; last value: {value!r}")
        time.sleep(0.25)


@pytest.fixture(scope="session")
def stack() -> Stack:
    env_file = Path(os.environ.get("PLOT_ENV_FILE", ROOT / ".env"))
    if not env_file.is_absolute():
        env_file = ROOT / env_file
    stack = Stack(env_file, read_env(env_file))
    with stack.api() as api:
        wait_for(lambda: _health(api), lambda h: h.get("status") == "ok")
    stack.exec("registrar", "plot", "seed", "provider")
    return stack


def _health(api: httpx.Client) -> dict[str, Any]:
    try:
        body: dict[str, Any] = api.get("/health").json()
        return body
    except httpx.HTTPError as err:
        return {"error": str(err)}


@pytest.fixture
def api(stack: Stack) -> Iterator[httpx.Client]:
    with stack.api() as client:
        yield client


@pytest.fixture
def name() -> Iterator[str]:
    """A fresh customer domain; everything with the ``it-`` prefix is reset afterwards."""
    yield f"it-{secrets.token_hex(4)}.com"


@pytest.fixture(autouse=True)
def cleanup(stack: Stack) -> Iterator[None]:
    yield
    with stack.api() as client:
        client.put("/admin/settings", json={"propagation_delay": 0, "flush_on_apply": True})
        client.post("/admin/reset", json={"prefix": "it-"})
