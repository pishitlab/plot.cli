"""Ports the services depend on; implementations live in ``plot.dns`` (SPEC §4.4)."""

from collections.abc import Collection
from typing import Protocol

from sqlalchemy.orm import Session

from plot.core.clock import Clock

__all__ = ["Clock", "DnsPublisher", "ResolverControl"]


class DnsPublisher(Protocol):
    def domains_changed(self, session: Session, domain_names: Collection[str]) -> None:
        """Snapshot the DNS view of ``domain_names`` from ``session`` now and schedule it.

        Called inside the caller's transaction after every change that may alter what the
        registry publishes (delegation or glue). The snapshot is taken at call time
        (R-PUB-01), so a domain that no longer exists is scheduled for removal.
        """
        ...


class ResolverControl(Protocol):
    def flush(self, domain_name: str | None = None) -> None:
        """Drop resolver cache for ``domain_name`` and below, or everything when ``None``."""
        ...
