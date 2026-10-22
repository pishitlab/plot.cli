"""In-memory implementations of the service ports for unit and API tests."""

from collections.abc import Collection

from sqlalchemy.orm import Session


class FakeDnsPublisher:
    def __init__(self) -> None:
        self.calls: list[frozenset[str]] = []

    def domains_changed(self, session: Session, domain_names: Collection[str]) -> None:
        self.calls.append(frozenset(domain_names))

    @property
    def changed(self) -> set[str]:
        """Every domain name reported since the last ``reset``."""
        return set().union(*self.calls)

    def reset(self) -> None:
        self.calls.clear()


class FakeResolverControl:
    def __init__(self) -> None:
        self.flushed: list[str | None] = []

    def flush(self, domain_name: str | None = None) -> None:
        self.flushed.append(domain_name)
