"""SPEC §16 Exit Gate P3 and §7.2 against the real compose stack (needs Docker)."""

import subprocess
import time
from collections.abc import Iterator

import dns.rcode
import dns.rdatatype
import httpx
import pytest

from tests.integration.conftest import Stack, wait_for

pytestmark = pytest.mark.integration

MYHOST = ["ns1.myhost.net", "ns2.myhost.net"]
DEMO_NS1, DEMO_NS2 = "172.28.0.31", "172.28.0.32"
LAN_SUBNET, LAN_UNBOUND, LAN_PROVIDER = "192.168.250.0/24", "192.168.250.2", "192.168.250.31"


def fqdns(names: list[str]) -> list[str]:
    return sorted(n + "." for n in names)


def registry_ns(stack: Stack, name: str) -> list[str]:
    reply = stack.registry(name)
    return sorted(
        r.to_text() for rrset in reply.authority if rrset.rdtype == dns.rdatatype.NS for r in rrset
    )


def test_all_services_up_and_healthy(stack: Stack, api: httpx.Client) -> None:
    running = stack.compose("ps", "--status", "running", "--services").stdout.split()
    assert sorted(running) == ["demo-ns1", "demo-ns2", "pdns-root", "registrar", "unbound"]
    assert api.get("/health").json() == {"status": "ok", "db": "ok", "pdns": "ok", "unbound": "ok"}


@pytest.mark.parametrize(
    ("option", "expected"),
    [
        ("module-config", "iterator"),
        ("qname-minimisation", "no"),
        ("harden-glue", "no"),
        ("harden-referral-path", "no"),
        ("harden-dnssec-stripped", "no"),
        ("do-not-query-localhost", "no"),
        ("do-ip6", "no"),
        ("cache-max-negative-ttl", "10"),
        ("cache-min-ttl", "0"),
        ("infra-host-ttl", "10"),
        ("verbosity", "1"),
        ("private-address", ""),
        ("trust-anchor-file", ""),
        ("auto-trust-anchor-file", ""),
        ("root-hints", "/etc/unbound/root.hints"),
    ],
)
def test_unbound_running_config_matches_spec_7_2(stack: Stack, option: str, expected: str) -> None:
    assert stack.unbound_option(option) == expected


def test_unbound_cache_max_ttl_access_control_and_forwards(stack: Stack) -> None:
    assert stack.unbound_option("cache-max-ttl") == stack.env.get("CACHE_MAX_TTL", "3600")
    conf = stack.exec("unbound", "cat", "/etc/unbound/unbound.conf")
    for line in [
        "access-control: 0.0.0.0/0 refuse",
        "access-control: 127.0.0.0/8 allow",
        "access-control: 10.0.0.0/8 allow",
        "access-control: 172.16.0.0/12 allow",
        "access-control: 192.168.0.0/16 allow",
    ]:
        assert line in conf
    forwards = stack.exec(
        "unbound", "unbound-control", "-c", "/etc/unbound/unbound.conf", "-s", "127.0.0.1@8953",
        "list_forwards",
    )  # fmt: skip
    upstream = stack.env.get("UPSTREAM_DNS", "1.1.1.1")
    assert f"github.com. IN forward {upstream}" in forwards
    # remote-control options are not readable with get_option; the plain-TCP client the
    # registrar uses only works because control-use-cert is off
    assert "control-use-cert: no" in conf
    with stack.api() as api:
        assert api.get("/health").json()["unbound"] == "ok"
    hints = stack.exec("unbound", "cat", "/etc/unbound/root.hints")
    assert stack.env.get("PDNS_ROOT_IP", "172.28.0.10") in hints


def test_passthrough_domain_resolves_upstream_and_is_reserved(
    stack: Stack, api: httpx.Client
) -> None:
    assert stack.resolve("github.com", "A") != []
    response = api.post("/domains", json={"name": "github.com", "owner": "it"})
    assert response.json()["error"]["code"] == "RESERVED_NAME"


def test_nxdomain_before_registration(stack: Stack, name: str) -> None:
    assert stack.rcode(name, "NS") == "NXDOMAIN"
    assert stack.rcode(f"www.{name}", "A") == "NXDOMAIN"
    assert dns.rcode.to_text(stack.registry(name).rcode()) == "NXDOMAIN"


def test_register_then_delegation_visible_through_resolver(
    stack: Stack, api: httpx.Client, name: str
) -> None:
    stack.provider_zone("demo-ns1", name, {"www": "10.20.30.40"})
    stack.provider_zone("demo-ns2", name, {"www": "10.20.30.40"})
    try:
        assert api.post("/domains", json={"name": name, "owner": "it"}).status_code == 201
        assert registry_ns(stack, name) == []  # registered without NS: no delegation (R-NS-05)
        assert (
            api.put(f"/domains/{name}/nameservers", json={"nameservers": MYHOST}).status_code == 200
        )
        assert wait_for(lambda: registry_ns(stack, name), bool) == fqdns(MYHOST)
        assert wait_for(lambda: stack.resolve(name, "NS"), bool) == fqdns(MYHOST)
        assert stack.resolve(f"www.{name}", "A") == ["10.20.30.40"]
        visible = api.get(f"/domains/{name}").json()["dns_visible"]
        assert visible["nameservers"] == MYHOST and visible["pending"] == []
    finally:
        stack.drop_zone("demo-ns1", name)
        stack.drop_zone("demo-ns2", name)


@pytest.fixture
def lan(stack: Stack) -> Iterator[None]:
    """Attach unbound and demo-ns1 to a 192.168.x.x network to test private glue."""
    network = "plot-it-lan"
    subprocess.run(["docker", "network", "rm", network], capture_output=True)
    subprocess.run(
        ["docker", "network", "create", "--subnet", LAN_SUBNET, network],
        check=True,
        capture_output=True,
    )
    for service, ip in (("unbound", LAN_UNBOUND), ("demo-ns1", LAN_PROVIDER)):
        subprocess.run(
            ["docker", "network", "connect", "--ip", ip, network, stack.container(service)],
            check=True,
            capture_output=True,
        )
    yield
    for service in ("unbound", "demo-ns1"):
        subprocess.run(
            ["docker", "network", "disconnect", network, stack.container(service)],
            capture_output=True,
        )
    subprocess.run(["docker", "network", "rm", network], capture_output=True)


def test_child_nameservers_with_192_168_glue_resolve(
    stack: Stack, api: httpx.Client, name: str, lan: None
) -> None:
    """U-003 / U-004: referral straight from the root to the domain, glue in 192.168.0.0/16."""
    ns = [f"ns1.{name}", f"ns2.{name}"]
    stack.exec("demo-ns1", "pdnsutil", "create-zone", name, ns[0])
    for record in (
        [ns[1], "NS"],
        ["ns1", "A", LAN_PROVIDER],
        ["ns2", "A", LAN_PROVIDER],
        ["www", "A", "10.1.1.1"],
    ):
        target = "@" if record[1] == "NS" else record[0]
        stack.exec("demo-ns1", "pdnsutil", "add-record", name, target, record[1], "60", record[-1])
    try:
        assert api.post("/domains", json={"name": name, "owner": "it"}).status_code == 201
        for host in ns:
            assert (
                api.post("/hosts", json={"name": host, "ipv4": [LAN_PROVIDER]}).status_code == 201
            )
        assert api.put(f"/domains/{name}/nameservers", json={"nameservers": ns}).status_code == 200
        reply = wait_for(lambda: stack.registry(name), lambda r: bool(r.additional))
        glue = sorted((rr.name.to_text(), r.to_text()) for rr in reply.additional for r in rr)
        assert glue == [(f"{ns[0]}.", LAN_PROVIDER), (f"{ns[1]}.", LAN_PROVIDER)]
        assert wait_for(lambda: stack.resolve(f"www.{name}", "A"), bool) == ["10.1.1.1"]
    finally:
        stack.drop_zone("demo-ns1", name)


def test_propagation_delay_holds_back_dns(stack: Stack, api: httpx.Client, name: str) -> None:
    delay = 5
    api.post("/domains", json={"name": name, "owner": "it"})
    api.put(f"/domains/{name}/overrides", json={"propagation_delay": delay})
    started = time.monotonic()
    body = api.put(f"/domains/{name}/nameservers", json={"nameservers": MYHOST}).json()
    assert body["nameservers"] == MYHOST  # DB changes at once (D-007)
    assert len(body["dns_visible"]["pending"]) == 1
    assert registry_ns(stack, name) == []
    wait_for(lambda: registry_ns(stack, name), bool)
    elapsed = time.monotonic() - started
    assert delay - 1 <= elapsed <= delay + 3, elapsed


def _two_providers(stack: Stack, name: str) -> tuple[list[str], list[str]]:
    a, b = [f"nsa1.{name}", f"nsa2.{name}"], [f"nsb1.{name}", f"nsb2.{name}"]
    for service, hosts, www in (("demo-ns1", a, "10.0.0.1"), ("demo-ns2", b, "10.0.0.2")):
        stack.exec(service, "pdnsutil", "create-zone", name, hosts[0])
        stack.exec(service, "pdnsutil", "add-record", name, "@", "NS", "60", hosts[1])
        stack.exec(service, "pdnsutil", "add-record", name, "www", "A", "300", www)
        for host in hosts:
            ip = DEMO_NS1 if service == "demo-ns1" else DEMO_NS2
            stack.exec(service, "pdnsutil", "add-record", name, host.split(".")[0], "A", "300", ip)
    return a, b


def test_resolver_flush_controls_visibility(stack: Stack, api: httpx.Client, name: str) -> None:
    a, b = _two_providers(stack, name)
    try:
        api.post("/domains", json={"name": name, "owner": "it"})
        for host in a:
            api.post("/hosts", json={"name": host, "ipv4": [DEMO_NS1]})
        for host in b:
            api.post("/hosts", json={"name": host, "ipv4": [DEMO_NS2]})
        api.put(f"/domains/{name}/nameservers", json={"nameservers": a})
        assert wait_for(lambda: stack.resolve(f"www.{name}", "A"), bool) == ["10.0.0.1"]

        # flush_on_apply=false: the resolver keeps serving the cached answer (S13)
        api.put("/admin/settings", json={"flush_on_apply": False})
        api.put(f"/domains/{name}/nameservers", json={"nameservers": b})
        wait_for(lambda: registry_ns(stack, name), lambda ns: ns == fqdns(b))
        assert stack.resolve(f"www.{name}", "A") == ["10.0.0.1"]
        api.post("/admin/resolver/flush", json={"domain": name})
        assert stack.resolve(f"www.{name}", "A") == ["10.0.0.2"]

        # flush_on_apply=true: applying the change flushes the domain (R-PUB-08)
        api.put("/admin/settings", json={"flush_on_apply": True})
        api.put(f"/domains/{name}/nameservers", json={"nameservers": a})
        assert wait_for(lambda: stack.resolve(f"www.{name}", "A"), lambda v: v == ["10.0.0.1"])
    finally:
        stack.drop_zone("demo-ns1", name)
        stack.drop_zone("demo-ns2", name)


def _zone_has(stack: Stack, name: str) -> bool:
    """Read zone '.' from pdns' database (no DNS answer cache in between)."""
    listing = stack.exec("pdns-root", "pdnsutil", "list-zone", ".")
    return any(line.startswith(f"{name}\t") for line in listing.splitlines())


def test_reconcile_after_restart(stack: Stack, api: httpx.Client, name: str) -> None:
    api.post("/domains", json={"name": name, "owner": "it", "nameservers": MYHOST})
    wait_for(lambda: _zone_has(stack, name), bool)

    # whole stack restart: data and DNS come back
    stack.compose("restart")
    wait_for(lambda: _health_status(stack), lambda s: s == "ok")
    assert wait_for(lambda: registry_ns(stack, name), bool) == fqdns(MYHOST)

    # drift in pdns is repaired by the reconcile the registrar runs when it starts (R-PUB-07)
    stack.exec("pdns-root", "pdnsutil", "delete-rrset", ".", f"{name}.", "NS")
    assert not _zone_has(stack, name)
    stack.compose("restart", "registrar")
    assert wait_for(lambda: _zone_has(stack, name), bool)


def _health_status(stack: Stack) -> str:
    try:
        with stack.api() as api:
            status: str = api.get("/health").json()["status"]
            return status
    except (httpx.HTTPError, ValueError):
        return "unreachable"
