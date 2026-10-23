"""Unbound cache control over the remote-control port (SPEC §7.2 ``control-use-cert: no``).

Protocol checked against unbound 1.26.1: one TCP connection per command, the client sends
``UBCT1 <command>\\n`` and unbound answers with text starting ``ok`` (or ``error ...``).
"""

import socket

PROTOCOL_PREFIX = "UBCT1 "


class UnboundControlError(Exception):
    pass


class UnboundControl:
    def __init__(self, host: str, port: int = 8953, timeout: float = 3.0) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout

    def command(self, command: str) -> str:
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as conn:
                conn.sendall(f"{PROTOCOL_PREFIX}{command}\n".encode())
                chunks = []
                while chunk := conn.recv(4096):
                    chunks.append(chunk)
        except OSError as err:
            raise UnboundControlError(f"unbound-control unreachable: {err}") from err
        reply = b"".join(chunks).decode(errors="replace")
        if reply.startswith("error"):
            raise UnboundControlError(reply.strip())
        return reply

    def flush(self, domain_name: str | None = None) -> None:
        """Drop cached data for ``domain_name`` and below, or the whole cache."""
        if domain_name is None:
            self._expect_ok("flush_zone .")
            self._expect_ok("flush_infra all")
        else:
            self._expect_ok(f"flush_zone {domain_name}")

    def ping(self) -> bool:
        try:
            return self.command("status").startswith("version:")
        except UnboundControlError:
            return False

    def _expect_ok(self, command: str) -> None:
        reply = self.command(command)
        if not reply.startswith("ok"):
            raise UnboundControlError(f"{command!r} -> {reply.strip()!r}")
