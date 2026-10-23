from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from plot.api.app import create_app
from plot.api.deps import AppState
from plot.core.clock import FakeClock
from plot.core.settings import RuntimeSettings
from plot.core.tlds import NamePolicy, SuffixRule
from plot.db.models import Base
from plot.db.session import make_engine, make_session_factory
from tests.conftest import T0
from tests.fakes import FakeDnsPublisher, FakeResolverControl

API_KEY = "test-key"


@pytest.fixture
def sessions() -> Iterator[sessionmaker[Session]]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture
def state(sessions: sessionmaker[Session]) -> AppState:
    return AppState(
        sessions=sessions,
        clock=FakeClock(T0),
        publisher=FakeDnsPublisher(),
        resolver=FakeResolverControl(),
        policy=NamePolicy(
            {"com": SuffixRule(), "net": SuffixRule(), "co.th": SuffixRule()}, {"github.com"}
        ),
        settings_defaults=RuntimeSettings(),
        api_key=SecretStr(API_KEY),
        health_probes={"pdns": lambda: True, "unbound": lambda: True},
    )


@pytest.fixture
def client(state: AppState) -> Iterator[TestClient]:
    with TestClient(create_app(state), headers={"X-API-Key": API_KEY}) as c:
        yield c


@pytest.fixture
def anon(state: AppState) -> Iterator[TestClient]:
    with TestClient(create_app(state)) as c:
        yield c


def set_probe(state: AppState, name: str, probe: Callable[[], bool]) -> None:
    state.health_probes[name] = probe
