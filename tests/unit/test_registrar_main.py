from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from plot.api import main
from plot.core.clock import FakeClock
from plot.core.settings import RuntimeSettings, load_env_config
from plot.core.tlds import NamePolicy
from plot.db.models import Base
from plot.db.session import make_engine, make_session_factory
from plot.dns.publisher import Publisher, PublishWorker
from plot.services.context import ServiceContext
from plot.services.domains import DomainService
from plot.services.events import RequestContext
from tests.fakes import FakeDnsPublisher, FakeResolverControl
from tests.unit.test_publisher import FakeRegistry

CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture
def sessions() -> sessionmaker[Session]:
    engine = make_engine("sqlite://")
    Base.metadata.create_all(engine)
    return make_session_factory(engine)


def test_lifecycle_tick_runs_job_at_most_every_interval(
    sessions: sessionmaker[Session], clock: FakeClock, policy: NamePolicy
) -> None:
    publisher = FakeDnsPublisher()
    with sessions.begin() as session:
        ctx = ServiceContext(
            session, clock, publisher, policy, RuntimeSettings(), RequestContext("t", "r")
        )
        DomainService(ctx).register("shop.com", "a")
    tick = main.LifecycleTick(sessions, clock, publisher, policy, RuntimeSettings())
    clock.advance(timedelta(days=366))
    publisher.reset()
    tick()
    assert publisher.changed == {"shop.com"}  # newly expired -> republished
    publisher.reset()
    clock.advance(1)
    tick()  # throttled
    assert publisher.calls == []
    clock.advance(main.LIFECYCLE_INTERVAL)
    tick()
    assert publisher.calls == []  # nothing new expired since the last run


class BrokenZone(FakeRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.fail_reconcile = True

    def ensure_root_zone(self, root_ip: str) -> None:
        if self.fail_reconcile:
            raise ConnectionError("pdns not up yet")


def test_worker_reconciles_before_first_publish_and_retries(
    sessions: sessionmaker[Session], clock: FakeClock
) -> None:
    zone = BrokenZone()
    publisher = Publisher(
        zone, FakeResolverControl(), clock, lambda s: RuntimeSettings(), root_ip="172.28.0.10"
    )
    worker = PublishWorker(sessions, publisher, interval=0.5)
    assert worker.run_once() == 1 and not worker.reconciled and not worker.healthy
    zone.fail_reconcile = False
    assert worker.run_once() == 0.5
    assert worker.reconciled and worker.healthy


def test_build_and_create_wire_the_registrar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("API_KEY", "k")
    monkeypatch.setenv("PDNS_API_KEY", "p")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONFIG_DIR", str(CONFIG))
    monkeypatch.setenv("PDNS_API_URL", "http://127.0.0.1:1")
    monkeypatch.setenv("UNBOUND_CONTROL_HOST", "127.0.0.1")
    monkeypatch.setenv("UNBOUND_CONTROL_PORT", "1")
    state, worker = main.build(load_env_config())
    assert (tmp_path / "data" / "registrar.db").exists()
    assert "com" in state.policy.suffixes
    assert state.settings_defaults == RuntimeSettings()
    assert not state.health_probes["pdns"]() and not state.health_probes["unbound"]()
    with TestClient(main.create(), headers={"X-API-Key": "k"}) as client:
        assert client.get("/api/v1/health").json()["status"] == "degraded"
        assert (
            client.post("/api/v1/domains", json={"name": "shop.com", "owner": "a"}).status_code
            == 201
        )
    worker.stop()
