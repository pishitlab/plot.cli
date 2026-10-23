"""Reference NS verifier (SPEC §11): has domain X been pointed at the expected nameservers?

The decision uses DNS only, as a hosting system would: the registry view (pdns-root, no
recursion) gives the parent delegation, the resolver gives what clients see, and every
parent nameserver is probed for an authoritative SOA. One thing DNS cannot tell is whether
a name without delegation is registered (both answer NXDOMAIN), so an optional
``is_registered`` lookup separates ``NOT_DELEGATED`` from ``NXDOMAIN`` (A-025).
"""

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from plot.core.names import normalize_name


class Status(StrEnum):
    NXDOMAIN = "NXDOMAIN"
    NOT_DELEGATED = "NOT_DELEGATED"
    MISMATCH = "MISMATCH"
    PARTIAL = "PARTIAL"
    LAME = "LAME"
    VERIFIED = "VERIFIED"
    ERROR = "ERROR"


class DnsUnreachable(Exception):
    pass


@dataclass(frozen=True)
class RegistryAnswer:
    nxdomain: bool
    nameservers: frozenset[str]


class DnsProbe(Protocol):
    def registry_ns(self, domain: str) -> RegistryAnswer:
        """Delegation of ``domain`` in the registry view; raises ``DnsUnreachable``."""
        ...

    def resolver_ns(self, domain: str) -> frozenset[str]:
        """NS of ``domain`` as the resolver answers (empty on NXDOMAIN/SERVFAIL);
        raises ``DnsUnreachable`` when the resolver does not answer at all."""
        ...

    def addresses(self, host: str) -> list[str]:
        """IPv4 addresses of a nameserver host through the resolver (empty if none)."""
        ...

    def authoritative_soa(self, address: str, domain: str) -> bool:
        """True when ``address`` answers SOA ``domain`` (no recursion) with AA=1."""
        ...


RegistrationLookup = Callable[[str], bool | None]  # None: unknown


@dataclass(frozen=True)
class Probe:
    nameserver: str
    addresses: list[str]
    ok: bool
    detail: str


@dataclass(frozen=True)
class Evidence:
    parent_ns: list[str]
    resolver_ns: list[str]
    registry_nxdomain: bool
    registered: bool | None
    probes: list[Probe] = field(default_factory=list)
    error: str | None = None


@dataclass(frozen=True)
class VerifyResult:
    domain: str
    expected: list[str]
    status: Status
    evidence: Evidence

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data


def verify(
    domain: str,
    expected: Iterable[str],
    dns: DnsProbe,
    is_registered: RegistrationLookup | None = None,
) -> VerifyResult:
    name = normalize_name(domain)
    want = frozenset(normalize_name(n) for n in expected)

    def result(status: Status, evidence: Evidence) -> VerifyResult:
        return VerifyResult(name, sorted(want), status, evidence)

    try:
        registry = dns.registry_ns(name)
        resolver = dns.resolver_ns(name)
    except DnsUnreachable as err:
        return result(Status.ERROR, Evidence([], [], False, None, error=str(err)))
    parent = registry.nameservers
    evidence = Evidence(sorted(parent), sorted(resolver), registry.nxdomain, None)

    if not parent:
        registered = is_registered(name) if is_registered is not None else None
        evidence = Evidence(evidence.parent_ns, evidence.resolver_ns, registry.nxdomain, registered)
        if registry.nxdomain and not registered:
            return result(Status.NXDOMAIN, evidence)
        return result(Status.NOT_DELEGATED, evidence)
    if not parent & want:
        return result(Status.MISMATCH, evidence)
    if parent != want:
        return result(Status.PARTIAL, evidence)

    probes = [_probe(dns, ns, name) for ns in sorted(parent)]
    evidence = Evidence(evidence.parent_ns, evidence.resolver_ns, False, None, probes)
    if not all(p.ok for p in probes):
        return result(Status.LAME, evidence)
    return result(Status.VERIFIED, evidence)


def _probe(dns: DnsProbe, nameserver: str, domain: str) -> Probe:
    """A nameserver passes when it resolves and every address answers authoritatively."""
    addresses = dns.addresses(nameserver)
    if not addresses:
        return Probe(nameserver, [], False, "nameserver name does not resolve")
    silent = [a for a in addresses if not dns.authoritative_soa(a, domain)]
    if silent:
        return Probe(
            nameserver, addresses, False, f"no authoritative answer from {', '.join(silent)}"
        )
    return Probe(nameserver, addresses, True, "authoritative")
