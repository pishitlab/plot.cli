from collections.abc import Iterator

import dns.flags
import dns.message
import dns.rcode
import dns.rrset
import pytest

from plot.scenarios.live import LiveScenarioDns
from plot.verifier.dns_probe import LiveDns
from tests.unit.test_dns_probe import serve


def answer(query: dns.message.Message) -> dns.message.Message:
    reply = dns.message.make_response(query)
    name = query.question[0].name.to_text()
    recursive = bool(query.flags & dns.flags.RD)
    if name == "shop.com." and not recursive:
        reply.authority.append(dns.rrset.from_text(name, 300, "IN", "NS", "ns1.shop.com."))
        reply.additional.append(
            dns.rrset.from_text("ns1.shop.com.", 300, "IN", "A", "192.168.1.10")
        )
    elif name == "www.shop.com." and recursive:
        reply.answer.append(dns.rrset.from_text(name, 60, "IN", "A", "10.0.0.2", "10.0.0.1"))
    else:
        reply.set_rcode(dns.rcode.NXDOMAIN)
    return reply


@pytest.fixture
def live() -> Iterator[LiveScenarioDns]:
    server, port = serve(answer)
    yield LiveScenarioDns(LiveDns(f"127.0.0.1:{port}", f"127.0.0.1:{port}"), timeout=0.3)
    server.shutdown()
    server.server_close()


def test_registry_referral_with_glue(live: LiveScenarioDns) -> None:
    result = live.ask("registry", "shop.com", "NS")
    assert (result.rcode, result.answers, result.glue) == (
        "NOERROR",
        ["ns1.shop.com."],
        ["ns1.shop.com. 192.168.1.10"],
    )


def test_resolver_answers_sorted_and_nxdomain(live: LiveScenarioDns) -> None:
    assert live.ask("resolver", "www.shop.com", "A").answers == ["10.0.0.1", "10.0.0.2"]
    assert live.ask("resolver", "never.com", "NS").rcode == "NXDOMAIN"


def test_timeout() -> None:
    dead = LiveScenarioDns(LiveDns("127.0.0.1:9", "127.0.0.1:9"), timeout=0.2)
    assert dead.ask("resolver", "x.com", "A").rcode == "TIMEOUT"
