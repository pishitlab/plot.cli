"""Verifier decisions for every status with fake DNS responses (SPEC §11, §16 P5)."""

from dataclasses import dataclass, field

import pytest

from plot.verifier.verify import DnsUnreachable, RegistryAnswer, Status, verify

EXPECTED = ["ns1.myhost.net", "ns2.myhost.net"]


@dataclass
class FakeDns:
    parent: set[str] = field(default_factory=set)
    nxdomain: bool = False
    resolver: set[str] = field(default_factory=set)
    addresses_of: dict[str, list[str]] = field(default_factory=dict)
    authoritative: set[str] = field(default_factory=set)
    registry_down: bool = False
    resolver_down: bool = False
    asked: list[str] = field(default_factory=list)

    def registry_ns(self, domain: str) -> RegistryAnswer:
        self.asked.append(f"registry {domain}")
        if self.registry_down:
            raise DnsUnreachable("registry timeout")
        return RegistryAnswer(self.nxdomain, frozenset(self.parent))

    def resolver_ns(self, domain: str) -> frozenset[str]:
        if self.resolver_down:
            raise DnsUnreachable("resolver timeout")
        return frozenset(self.resolver)

    def addresses(self, host: str) -> list[str]:
        return self.addresses_of.get(host, [])

    def authoritative_soa(self, address: str, domain: str) -> bool:
        return address in self.authoritative


def healthy(parent: set[str]) -> FakeDns:
    return FakeDns(
        parent=parent,
        resolver=parent,
        addresses_of={"ns1.myhost.net": ["172.28.0.31"], "ns2.myhost.net": ["172.28.0.32"]},
        authoritative={"172.28.0.31", "172.28.0.32"},
    )


def test_nxdomain_when_not_in_registry_and_not_registered() -> None:
    result = verify("never.com", EXPECTED, FakeDns(nxdomain=True), lambda name: False)
    assert result.status is Status.NXDOMAIN
    assert result.evidence.registered is False and result.evidence.registry_nxdomain


def test_nxdomain_without_registration_lookup() -> None:
    assert verify("never.com", EXPECTED, FakeDns(nxdomain=True)).status is Status.NXDOMAIN


def test_not_delegated_when_registered_without_ns() -> None:
    # DNS answers NXDOMAIN for a registered domain without delegation (S03, S06, S09, S10)
    result = verify("shop.com", EXPECTED, FakeDns(nxdomain=True), lambda name: True)
    assert result.status is Status.NOT_DELEGATED
    assert result.evidence.registered is True


def test_not_delegated_when_name_exists_without_ns() -> None:
    assert verify("shop.com", EXPECTED, FakeDns(nxdomain=False)).status is Status.NOT_DELEGATED


def test_mismatch_when_no_expected_ns() -> None:
    result = verify("shop.com", EXPECTED, healthy({"ns1.other.net", "ns2.other.net"}))
    assert result.status is Status.MISMATCH
    assert result.evidence.parent_ns == ["ns1.other.net", "ns2.other.net"]


@pytest.mark.parametrize(
    "parent",
    [
        {"ns1.myhost.net", "ns1.other.net"},  # S05
        {"ns1.myhost.net"},
        {"ns1.myhost.net", "ns2.myhost.net", "ns3.other.net"},
    ],
)
def test_partial_when_sets_overlap_but_differ(parent: set[str]) -> None:
    assert verify("shop.com", EXPECTED, healthy(parent)).status is Status.PARTIAL


def test_lame_when_a_nameserver_does_not_answer() -> None:
    dns = healthy(set(EXPECTED))
    dns.authoritative = {"172.28.0.31"}
    result = verify("shop.com", EXPECTED, dns)
    assert result.status is Status.LAME
    probes = {p.nameserver: p for p in result.evidence.probes}
    assert probes["ns1.myhost.net"].ok
    assert not probes["ns2.myhost.net"].ok
    assert probes["ns2.myhost.net"].detail == "no authoritative answer from 172.28.0.32"


def test_lame_when_nameserver_name_does_not_resolve() -> None:
    dns = healthy(set(EXPECTED))
    del dns.addresses_of["ns2.myhost.net"]
    result = verify("shop.com", EXPECTED, dns)
    assert result.status is Status.LAME
    assert result.evidence.probes[1].detail == "nameserver name does not resolve"


def test_verified_with_normalized_set_comparison() -> None:
    result = verify("Shop.COM.", ["NS2.MyHost.NET.", "ns1.myhost.net"], healthy(set(EXPECTED)))
    assert result.status is Status.VERIFIED
    assert result.domain == "shop.com"
    assert result.expected == EXPECTED
    assert all(p.ok for p in result.evidence.probes)
    assert result.to_dict()["status"] == "VERIFIED"
    assert result.to_dict()["evidence"]["probes"][0] == {
        "nameserver": "ns1.myhost.net",
        "addresses": ["172.28.0.31"],
        "ok": True,
        "detail": "authoritative",
    }


@pytest.mark.parametrize("down", ["registry_down", "resolver_down"])
def test_error_when_registry_or_resolver_unreachable(down: str) -> None:
    dns = healthy(set(EXPECTED))
    setattr(dns, down, True)
    result = verify("shop.com", EXPECTED, dns)
    assert result.status is Status.ERROR
    assert result.evidence.error is not None and "timeout" in result.evidence.error


def test_every_status_is_covered() -> None:
    covered = {
        verify("a.com", EXPECTED, FakeDns(nxdomain=True)).status,
        verify("a.com", EXPECTED, FakeDns(nxdomain=True), lambda n: True).status,
        verify("a.com", EXPECTED, healthy({"x.net"})).status,
        verify("a.com", EXPECTED, healthy({"ns1.myhost.net"})).status,
        verify("a.com", EXPECTED, FakeDns(parent=set(EXPECTED))).status,
        verify("a.com", EXPECTED, healthy(set(EXPECTED))).status,
        verify("a.com", EXPECTED, FakeDns(registry_down=True)).status,
    }
    assert covered == set(Status)
