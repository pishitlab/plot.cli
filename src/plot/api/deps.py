"""Application state and per-request dependencies."""

import hmac
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from fastapi import Request
from pydantic import SecretStr
from sqlalchemy.orm import Session, sessionmaker

from plot.core.errors import Unauthorized
from plot.core.settings import RuntimeSettings
from plot.core.tlds import NamePolicy
from plot.services.context import ServiceContext
from plot.services.events import RequestContext
from plot.services.ports import Clock, DnsPublisher, ResolverControl
from plot.services.settings import load_settings

API_KEY_HEADER = "X-API-Key"
API_ACTOR = "api"


@dataclass
class AppState:
    sessions: sessionmaker[Session]
    clock: Clock
    publisher: DnsPublisher
    resolver: ResolverControl
    policy: NamePolicy
    settings_defaults: RuntimeSettings
    api_key: SecretStr
    # name -> probe returning True when the dependency is reachable (reported by /health)
    health_probes: dict[str, Callable[[], bool]] = field(default_factory=dict)


def get_state(request: Request) -> AppState:
    state: AppState = request.app.state.plot
    return state


def request_id(request: Request) -> str:
    rid: str = request.state.request_id
    return rid


def require_api_key(request: Request) -> None:
    """D-008: single shared key, compared in constant time."""
    supplied = request.headers.get(API_KEY_HEADER, "")
    expected = get_state(request).api_key.get_secret_value()
    if not supplied or not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise Unauthorized()


@contextmanager
def unit_of_work(request: Request) -> Iterator[ServiceContext]:
    """One transaction per request: commit on success, roll back on any error."""
    state = get_state(request)
    with state.sessions() as session:
        ctx = ServiceContext(
            session=session,
            clock=state.clock,
            publisher=state.publisher,
            policy=state.policy,
            settings=load_settings(session, state.settings_defaults),
            request=RequestContext(actor=API_ACTOR, request_id=request_id(request)),
        )
        try:
            yield ctx
            session.commit()
        except BaseException:
            session.rollback()
            raise
