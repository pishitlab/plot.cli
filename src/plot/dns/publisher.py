"""``DnsPublisher`` implementation: projector + scheduler + registry client (SPEC §6.5)."""

import logging
import threading
from collections.abc import Callable, Collection
from typing import Protocol

from sqlalchemy.orm import Session, sessionmaker

from plot.core.clock import Clock
from plot.core.settings import RuntimeSettings
from plot.dns.projector import Snapshot, project
from plot.dns.reconcile import ZoneAccess, reconcile
from plot.dns.scheduler import (
    Backoff,
    RunResult,
    apply_due,
    has_pending,
    propagation_delay,
    published_snapshot,
    schedule_change,
)
from plot.services.ports import ResolverControl

log = logging.getLogger("plot.dns")

SettingsLoader = Callable[[Session], RuntimeSettings]


class Registry(ZoneAccess, Protocol):
    def apply(self, domain: str, old: Snapshot, new: Snapshot) -> None: ...


class Publisher:
    def __init__(
        self,
        registry: Registry,
        resolver: ResolverControl,
        clock: Clock,
        settings: SettingsLoader,
        root_ip: str,
    ) -> None:
        self.root_ip = root_ip
        self.registry = registry
        self.resolver = resolver
        self.clock = clock
        self.settings = settings

    def domains_changed(self, session: Session, domain_names: Collection[str]) -> None:
        """Snapshot now (R-PUB-01) and schedule at now + delay (R-PUB-05). No registry I/O,
        so API calls succeed even while pdns is down (R-PUB-09)."""
        settings = self.settings(session)
        now = self.clock.now()
        for name in sorted(domain_names):
            snapshot = project(session, name, now, settings)
            if not has_pending(session, name) and snapshot == published_snapshot(session, name):
                continue  # nothing would change in DNS
            schedule_change(
                session, name, snapshot, now, propagation_delay(session, name, settings)
            )

    def reconcile(self, session: Session) -> list[str]:
        """R-PUB-07: repair zone drift from ``published_state`` and flush what was fixed."""
        fixed = reconcile(session, self.registry, self.root_ip)
        self._flush(session, fixed)
        return fixed

    def apply_due(self, session: Session) -> RunResult:
        result = apply_due(session, self.clock.now(), self.registry.apply)
        self._flush(session, result.applied)
        return result

    def _flush(self, session: Session, names: list[str]) -> None:
        """R-PUB-08: resolvers must not keep serving the old delegation from cache."""
        if not names or not self.settings(session).flush_on_apply:
            return
        for name in names:
            try:
                self.resolver.flush(name)
            except Exception:
                log.warning("resolver flush failed for %s", name, exc_info=True)


class PublishWorker:
    """Background thread applying due changes; retries with backoff while pdns fails."""

    def __init__(
        self,
        sessions: sessionmaker[Session],
        publisher: Publisher,
        *,
        interval: float = 0.5,
        on_tick: Callable[[], None] | None = None,
    ) -> None:
        self.sessions = sessions
        self.publisher = publisher
        self.interval = interval
        self.on_tick = on_tick
        self.backoff = Backoff()
        self.healthy = True
        self.reconciled = False  # R-PUB-07: reconcile once before the first publish pass
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> float:
        """One pass; returns how long to wait before the next one."""
        if self.on_tick is not None:
            try:
                self.on_tick()
            except Exception:
                log.exception("tick hook failed")
        if not self.reconciled:
            try:
                with self.sessions.begin() as session:
                    fixed = self.publisher.reconcile(session)
            except Exception as err:
                self.healthy = False
                delay = self.backoff.failed()
                log.warning("reconcile failed, retrying in %.0fs: %s", delay, err)
                return delay
            self.reconciled = True
            log.info("reconciled registry zone, fixed: %s", fixed)
        with self.sessions.begin() as session:
            result = self.publisher.apply_due(session)
        if result.error is None:
            self.healthy = True
            self.backoff.reset()
            return self.interval
        self.healthy = False
        delay = self.backoff.failed()
        log.warning("publish failed, retrying in %.0fs: %s", delay, result.error)
        return delay

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="plot-publisher", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                delay = self.run_once()
            except Exception:
                log.exception("publish worker pass failed")
                self.healthy = False
                delay = self.backoff.failed()
            self._stop.wait(delay)
