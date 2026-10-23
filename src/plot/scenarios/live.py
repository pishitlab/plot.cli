"""Real DNS for scenario ``dns`` steps (resolver with recursion, registry view without)."""

import dns.exception
import dns.flags
import dns.message
import dns.query
import dns.rcode
import dns.rdatatype

from plot.scenarios.engine import DnsAnswer
from plot.verifier.dns_probe import LiveDns

TIMEOUT = 5.0


class LiveScenarioDns:
    def __init__(self, probe: LiveDns, timeout: float = TIMEOUT) -> None:
        self.servers = {"resolver": probe.resolver_addr, "registry": probe.registry_addr}
        self.timeout = timeout

    def ask(self, server: str, name: str, rtype: str) -> DnsAnswer:
        host, port = self.servers[server]
        query = dns.message.make_query(name, rtype)
        if server == "registry":
            query.flags &= ~dns.flags.RD
        try:
            reply = dns.query.udp(query, host, port=port, timeout=self.timeout)
        except (dns.exception.Timeout, OSError):
            return DnsAnswer("TIMEOUT", [], [])
        wanted = dns.rdatatype.from_text(rtype)
        sections = (reply.answer, reply.authority) if server == "registry" else (reply.answer,)
        answers = [
            r.to_text()
            for section in sections
            for rrset in section
            if rrset.rdtype == wanted
            for r in rrset
        ]
        glue = [
            f"{rrset.name.to_text()} {r.to_text()}" for rrset in reply.additional for r in rrset
        ]
        return DnsAnswer(dns.rcode.to_text(reply.rcode()), sorted(answers), sorted(glue))
