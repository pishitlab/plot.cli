from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import text

from plot.api.deps import get_state

router = APIRouter()

Probe = Literal["ok", "down"]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    db: Probe
    pdns: Probe
    unbound: Probe


@router.get("/health", response_model=Health)
def health(request: Request) -> Health:
    """No API key required. Reports degraded when any dependency is unreachable (R-PUB-09)."""
    state = get_state(request)
    results: dict[str, Probe] = {"db": "ok" if _db_ok(request) else "down"}
    for name in ("pdns", "unbound"):
        probe = state.health_probes.get(name)
        results[name] = "ok" if probe is not None and _safe(probe) else "down"
    status: Literal["ok", "degraded"] = (
        "ok" if all(v == "ok" for v in results.values()) else "degraded"
    )
    return Health(status=status, **results)


def _db_ok(request: Request) -> bool:
    def probe() -> bool:
        with get_state(request).sessions() as session:
            session.execute(text("SELECT 1"))
        return True

    return _safe(probe)


def _safe(probe: Callable[[], bool]) -> bool:
    try:
        return bool(probe())
    except Exception:
        return False
