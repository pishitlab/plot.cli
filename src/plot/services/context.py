"""Dependencies shared by every service call."""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from plot.core.settings import RuntimeSettings
from plot.core.tlds import NamePolicy
from plot.db.models import Event
from plot.services.events import RequestContext, record_event
from plot.services.ports import Clock, DnsPublisher


@dataclass
class ServiceContext:
    """One unit of work. Services flush but never commit: the caller owns the transaction."""

    session: Session
    clock: Clock
    publisher: DnsPublisher
    policy: NamePolicy
    settings: RuntimeSettings
    request: RequestContext

    def record(
        self,
        action: str,
        *,
        domain_name: str | None = None,
        host_name: str | None = None,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> Event:
        return record_event(
            self.session,
            self.clock,
            self.request,
            action,
            domain_name=domain_name,
            host_name=host_name,
            before=before,
            after=after,
        )
