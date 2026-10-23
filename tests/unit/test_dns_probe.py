"""LiveDns against tiny in-process UDP DNS servers built with dnspython."""

import socketserver
import threading
from collections.abc import Callable, Iterator

import dns.flags
import dns.message
import dns.rcode
import dns.rrset
import pytest

from plot.verifier.dns_probe import LiveDns, split_addr
from plot.verifier.verify import DnsUnreachable

Answer = Callable[[dns.message.Message], dns.message.Message | None]


def serve(answer: Answer) -> tuple[socketserver.UDPServer, int]:
    class Handler(socketserver.BaseRequestHandler):
        def handle(self) -> None:
            data, sock = self.request
            reply = answer(dns.message.from_wire(data))
            if reply is not None:
                sock.sendto(reply.to_wire(), self.client_address)

    server = socketserver.UDPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_address[1]


def registry_answer(query: dns.message.Message) -> dns.message.Message:
    reply = dns.message.make_response(query)
    qname = query.question[0].name.to_text()
    if qname == "shop.com.":
        reply.authority.append(
            dns.rrset.from_text("shop.com.", 300, "IN", "NS", "NS1.MyHost.net.", "ns2.myhost.net.")
        )
    elif qname == "ns1.shop.com.":
        reply.answer.append(dns.rrset.from_text("ns1.shop.com.", 300, "IN", "A", "10.0.0.1"))
    else:
        reply.set_rcode(dns.rcode.NXDOMAIN)
    assert not query.flags & dns.flags.RD  # +norec
    return reply


def resolver_answer(query: dns.message.Message) -> dns.message.Message | None:
    reply = dns.message.make_response(query)
    qname, qtype = query.question[0].name.to_text(), query.question[0].rdtype
    if qname == "lame.com.":
        return None  # resolver still chasing a lame server
    if qname == "shop.com." and qtype == dns.rdatatype.NS:
        reply.answer.append(dns.rrset.from_text("shop.com.", 300, "IN", "NS", "ns1.myhost.net."))
    elif qname == "ns1.myhost.net.":
        reply.answer.append(dns.rrset.from_text(qname, 300, "IN", "A", "127.0.0.1"))
    elif qname == "shop.com." and qtype == dns.rdatatype.SOA:
        reply.flags |= dns.flags.AA
        reply.answer.append(
            dns.rrset.from_text(qname, 300, "IN", "SOA", "ns1.myhost.net. h. 1 2 3 4 5")
        )
    elif qname == "notauth.com.":
        reply.answer.append(
            dns.rrset.from_text(qname, 300, "IN", "SOA", "ns1.myhost.net. h. 1 2 3 4 5")
        )
    elif qname == ".":
        reply.answer.append(dns.rrset.from_text(".", 300, "IN", "SOA", "a.root. h. 1 2 3 4 5"))
    else:
        reply.set_rcode(dns.rcode.NXDOMAIN)
    return reply


@pytest.fixture
def live() -> Iterator[LiveDns]:
    registry, registry_port = serve(registry_answer)
    resolver, resolver_port = serve(resolver_answer)
    yield LiveDns(
        f"127.0.0.1:{resolver_port}",
        f"127.0.0.1:{registry_port}",
        timeout=0.3,
        probe_port=resolver_port,
    )
    for server in (registry, resolver):
        server.shutdown()
        server.server_close()


def test_registry_view(live: LiveDns) -> None:
    referral = live.registry_ns("shop.com")
    assert not referral.nxdomain
    assert referral.nameservers == {"ns1.myhost.net", "ns2.myhost.net"}
    assert live.registry_ns("never.com").nxdomain
    no_ns = live.registry_ns("ns1.shop.com")
    assert (no_ns.nxdomain, no_ns.nameservers) == (False, frozenset())


def test_resolver_answers(live: LiveDns) -> None:
    assert live.resolver_ns("shop.com") == {"ns1.myhost.net"}
    assert live.resolver_ns("never.com") == frozenset()
    assert live.resolver_ns("lame.com") == frozenset()  # timeout, but the resolver is alive
    assert live.addresses("ns1.myhost.net") == ["127.0.0.1"]
    assert live.addresses("nothing.net") == []


def test_authoritative_probe(live: LiveDns) -> None:
    assert live.authoritative_soa("127.0.0.1", "shop.com")
    assert not live.authoritative_soa("127.0.0.1", "notauth.com")  # AA=0
    assert not live.authoritative_soa("127.0.0.1", "never.com")  # NXDOMAIN


def test_unreachable_servers() -> None:
    dead = LiveDns("127.0.0.1:9", "127.0.0.1:9", timeout=0.2, probe_port=9)
    with pytest.raises(DnsUnreachable):
        dead.registry_ns("shop.com")
    with pytest.raises(DnsUnreachable):
        dead.resolver_ns("shop.com")
    assert not dead.authoritative_soa("127.0.0.1", "shop.com")


def test_from_env_and_addresses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PLOT_RESOLVER", "10.0.0.53")
    monkeypatch.setenv("PLOT_REGISTRY_ADDR", "10.0.0.53:5300")
    live = LiveDns.from_env()
    assert (live.resolver_addr, live.registry_addr) == (("10.0.0.53", 53), ("10.0.0.53", 5300))
    monkeypatch.delenv("PLOT_RESOLVER")
    monkeypatch.delenv("PLOT_REGISTRY_ADDR")
    assert LiveDns.from_env().registry_addr == ("192.168.1.175", 5300)
    assert split_addr("2001:db8::1", 53) == ("2001:db8::1", 53)
