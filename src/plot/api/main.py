"""Composition root of the registrar process (``uvicorn --factory plot.api.main:create``)."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import httpx
from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from plot.api.app import create_app
from plot.api.deps import AppState
from plot.cli.client import ApiClient
from plot.core.clock import Clock, SystemClock
from plot.core.settings import EnvConfig, RuntimeSettings, load_env_config, load_runtime_defaults
from plot.core.tlds import NamePolicy, load_name_policy
from plot.db.session import make_engine, make_session_factory, migrate, sqlite_url
from plot.dns.pdns_client import PdnsClient
from plot.dns.publisher import Publisher, PublishWorker
from plot.dns.unbound_ctl import UnboundControl
from plot.services.context import ServiceContext
from plot.services.events import RequestContext
from plot.services.lifecycle import LifecycleService
from plot.services.ports import DnsPublisher
from plot.services.settings import load_settings
from plot.web.app import mount_web_ui

LIFECYCLE_INTERVAL = timedelta(seconds=5)
SYSTEM_ACTOR = "system"

log = logging.getLogger("plot.registrar")


class LifecycleTick:
    """Runs the R-DOM-06 lifecycle job from the publish worker at most every few seconds."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        clock: Clock,
        publisher: DnsPublisher,
        policy: NamePolicy,
        defaults: RuntimeSettings,
    ) -> None:
        self.sessions, self.clock, self.publisher = sessions, clock, publisher
        self.policy, self.defaults = policy, defaults
        self.last_run: datetime | None = None

    def __call__(self) -> None:
        now = self.clock.now()
        if self.last_run is not None and now - self.last_run < LIFECYCLE_INTERVAL:
            return
        with self.sessions.begin() as session:
            ctx = ServiceContext(
                session=session,
                clock=self.clock,
                publisher=self.publisher,
                policy=self.policy,
                settings=load_settings(session, self.defaults),
                request=RequestContext(actor=SYSTEM_ACTOR, request_id="lifecycle"),
            )
            result = LifecycleService(ctx).run(since=self.last_run)
        if result.purged or result.expired:
            log.info("lifecycle: expired=%s purged=%s", result.expired, result.purged)
        self.last_run = now


def build(config: EnvConfig) -> tuple[AppState, PublishWorker]:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    engine = make_engine(sqlite_url(config.data_dir))
    migrate(engine)
    sessions = make_session_factory(engine)
    clock = SystemClock()
    policy = load_name_policy(config.config_dir / "tlds.yml", config.config_dir / "passthrough.txt")
    defaults = load_runtime_defaults(config.config_dir / "settings.default.yml")
    pdns = PdnsClient(config.pdns_api_url, config.pdns_api_key.get_secret_value())
    unbound = UnboundControl(config.unbound_control_host, config.unbound_control_port)
    publisher = Publisher(
        pdns,
        unbound,
        clock,
        lambda session: load_settings(session, defaults),
        root_ip=str(config.pdns_root_ip),
    )
    worker = PublishWorker(
        sessions,
        publisher,
        on_tick=LifecycleTick(sessions, clock, publisher, policy, defaults),
    )
    state = AppState(
        sessions=sessions,
        clock=clock,
        publisher=publisher,
        resolver=unbound,
        policy=policy,
        settings_defaults=defaults,
        api_key=config.api_key,
        health_probes={
            "pdns": lambda: pdns.ping() and worker.healthy,
            "unbound": unbound.ping,
        },
    )
    return state, worker


def create() -> FastAPI:
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    state, worker = build(load_env_config())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        worker.start()
        yield
        worker.stop()

    app = create_app(state)
    app.router.lifespan_context = lifespan
    api_url = os.environ.get("PLOT_API_URL", "http://localhost:8080")
    mount_web_ui(
        app,
        lambda key: ApiClient(
            httpx.Client(base_url=api_url, headers={"X-API-Key": key}, timeout=60)
        ),
    )
    return app
