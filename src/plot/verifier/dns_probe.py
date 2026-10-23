"""``DnsProbe`` over real DNS with dnspython (SPEC §11: +norec probes, 3 s timeout, 1 retry)."""

import os

import dns.exception
import dns.flags
import dns.message
import dns.name
import dns.query
import dns.rcode
import dns.rdatatype
import dns.resolver

from plot.verifier.verify import DnsUnreachable, RegistryAnswer

TIMEOUT = 3.0
RETRIES = 1
DEFAULT_RESOLVER = "192.168.1.175"
DEFAULT_REGISTRY = "192.168.1.175:5300"


def split_addr(value: str, default_port: int) -> tuple[str, int]:
    host, sep, port = value.rpartition(":")
    if sep and host and port.isdigit() and ":" not in host:
        return host, int(port)
    return value, default_port


class LiveDns:
    def __init__(
        self, resolver: str, registry: str, *, timeout: float = TIMEOUT, probe_port: int = 53
    ) -> None:
        self.resolver_addr = split_addr(resolver, 53)
        self.registry_addr = split_addr(registry, 53)
        self.timeout = timeout
        self.probe_port = probe_port

    @classmethod
    def from_env(cls) -> "LiveDns":
        return cls(
            os.environ.get("PLOT_RESOLVER", DEFAULT_RESOLVER),
            os.environ.get("PLOT_REGISTRY_ADDR", DEFAULT_REGISTRY),
        )

    def _query(self, address: tuple[str, int], qname: str, rdtype: str) -> dns.message.Message:
        query = dns.message.make_query(qname, rdtype)
        query.flags &= ~dns.flags.RD
        failure: Exception | None = None
        for _ in range(RETRIES + 1):
            try:
                return dns.query.udp(query, address[0], port=address[1], timeout=self.timeout)
            except (dns.exception.Timeout, OSError) as err:
                failure = err
        raise DnsUnreachable(f"no answer from {address[0]}:{address[1]}: {failure}") from failure

    def registry_ns(self, domain: str) -> RegistryAnswer:
        reply = self._query(self.registry_addr, domain, "NS")
        owner = dns.name.from_text(domain)
        nameservers = frozenset(
            rdata.target.to_text(omit_final_dot=True).lower()
            for section in (reply.answer, reply.authority)
            for rrset in section
            if rrset.rdtype == dns.rdatatype.NS and rrset.name == owner
            for rdata in rrset
        )
        return RegistryAnswer(reply.rcode() == dns.rcode.NXDOMAIN, nameservers)

    def _resolver(self) -> dns.resolver.Resolver:
        resolver = dns.resolver.Resolver(configure=False)
        resolver.nameservers = [self.resolver_addr[0]]
        resolver.port = self.resolver_addr[1]
        resolver.lifetime = self.timeout * (RETRIES + 1)
        resolver.cache = None
        return resolver

    def resolver_ns(self, domain: str) -> frozenset[str]:
        try:
            answer = self._resolver().resolve(domain, "NS")
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
            return frozenset()
        except dns.exception.Timeout:
            # A lame delegation can outlast our timeout; only an unresponsive resolver is fatal.
            self._query(self.resolver_addr, ".", "SOA")
            return frozenset()
        return frozenset(r.target.to_text(omit_final_dot=True).lower() for r in answer)

    def addresses(self, host: str) -> list[str]:
        try:
            return sorted(r.to_text() for r in self._resolver().resolve(host, "A"))
        except dns.exception.DNSException:
            return []

    def authoritative_soa(self, address: str, domain: str) -> bool:
        try:
            reply = self._query((address, self.probe_port), domain, "SOA")
        except DnsUnreachable:
            return False
        return (
            bool(reply.flags & dns.flags.AA)
            and reply.rcode() == dns.rcode.NOERROR
            and any(r.rdtype == dns.rdatatype.SOA for r in reply.answer)
        )
