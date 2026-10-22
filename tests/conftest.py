from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from plot.core.clock import FakeClock
from plot.core.settings import RuntimeSettings
from plot.core.tlds import NamePolicy, SuffixRule
from plot.db.models import Base
from plot.db.session import make_engine, make_session_factory
from plot.services.context import ServiceContext
from plot.services.events import RequestContext
from tests.fakes import FakeDnsPublisher

T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        yield session
    engine.dispose()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(T0)


@pytest.fixture
def publisher() -> FakeDnsPublisher:
    return FakeDnsPublisher()


@pytest.fixture
def policy() -> NamePolicy:
    return NamePolicy(
        {"com": SuffixRule(), "net": SuffixRule(), "th": SuffixRule(1), "co.th": SuffixRule()},
        {"github.com"},
    )


@pytest.fixture
def ctx(
    session: Session, clock: FakeClock, publisher: FakeDnsPublisher, policy: NamePolicy
) -> ServiceContext:
    return ServiceContext(
        session=session,
        clock=clock,
        publisher=publisher,
        policy=policy,
        settings=RuntimeSettings(),
        request=RequestContext(actor="test", request_id="req-1"),
    )
