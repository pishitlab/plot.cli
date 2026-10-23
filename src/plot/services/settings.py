"""Runtime settings persisted in the ``settings`` table over the file defaults (SPEC §13.4)."""

from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from plot.core.errors import ValidationFailed
from plot.core.settings import RuntimeSettings
from plot.db.models import Setting
from plot.services.events import RequestContext, record_event
from plot.services.ports import Clock

FIELDS = tuple(RuntimeSettings.model_fields)


def load_settings(session: Session, defaults: RuntimeSettings) -> RuntimeSettings:
    stored = {
        row.key: row.value
        for row in session.scalars(select(Setting).where(Setting.key.in_(FIELDS)))
    }
    return RuntimeSettings.model_validate({**defaults.model_dump(), **stored})


def update_settings(
    session: Session,
    clock: Clock,
    request: RequestContext,
    defaults: RuntimeSettings,
    changes: dict[str, Any],
) -> RuntimeSettings:
    """Validate and persist ``changes`` (a subset of the settings fields)."""
    before = load_settings(session, defaults)
    try:
        after = RuntimeSettings.model_validate({**before.model_dump(), **changes})
    except ValidationError as err:
        raise ValidationFailed(
            "invalid settings", errors=[{"loc": e["loc"], "msg": e["msg"]} for e in err.errors()]
        ) from None
    for key, value in after.model_dump().items():
        row = session.get(Setting, key)
        if row is None:
            session.add(Setting(key=key, value=value))
        else:
            row.value = value
    session.flush()
    record_event(
        session,
        clock,
        request,
        "settings.update",
        before=before.model_dump(),
        after=after.model_dump(),
    )
    return after
