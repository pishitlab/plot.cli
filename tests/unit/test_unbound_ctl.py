import socketserver
import threading
from collections.abc import Iterator
from typing import ClassVar

import pytest

from plot.dns.unbound_ctl import UnboundControl, UnboundControlError

REPLIES = {
    "status": "version: 1.26.1\nverbosity: 1\n",
    "flush_zone shop.com": "ok removed 3 rrsets, 2 messages and 0 key entries\n",
    "flush_zone .": "ok removed 4 rrsets, 3 messages and 0 key entries\n",
    "flush_infra all": "ok\n",
    "weird": "something else\n",
}


class FakeUnbound(socketserver.StreamRequestHandler):
    received: ClassVar[list[str]] = []

    def handle(self) -> None:
        line = self.rfile.readline().decode()
        assert line.startswith("UBCT1 ") and line.endswith("\n")
        command = line[len("UBCT1 ") : -1]
        self.received.append(command)
        self.wfile.write(REPLIES.get(command, f"error unknown command '{command}'\n").encode())


@pytest.fixture
def control() -> Iterator[UnboundControl]:
    FakeUnbound.received = []
    server = socketserver.TCPServer(("127.0.0.1", 0), FakeUnbound)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield UnboundControl("127.0.0.1", server.server_address[1])
    server.shutdown()
    server.server_close()


def test_flush_domain(control: UnboundControl) -> None:
    control.flush("shop.com")
    assert FakeUnbound.received == ["flush_zone shop.com"]


def test_flush_everything(control: UnboundControl) -> None:
    control.flush()
    assert FakeUnbound.received == ["flush_zone .", "flush_infra all"]


def test_ping(control: UnboundControl) -> None:
    assert control.ping()


def test_error_replies_raise(control: UnboundControl) -> None:
    with pytest.raises(UnboundControlError, match="unknown command"):
        control.command("bogus")
    with pytest.raises(UnboundControlError, match="something else"):
        control._expect_ok("weird")


def test_unreachable() -> None:
    dead = UnboundControl("127.0.0.1", 1, timeout=0.5)
    with pytest.raises(UnboundControlError, match="unreachable"):
        dead.flush("shop.com")
    assert not dead.ping()
