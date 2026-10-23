from fastapi import APIRouter, Request

from plot.api import schemas
from plot.api.deps import get_state, unit_of_work
from plot.api.routes.domains import to_schema
from plot.core.names import normalize_name
from plot.services.domains import DomainService
from plot.services.lifecycle import LifecycleService
from plot.services.settings import update_settings

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/settings", response_model=schemas.Settings)
def get_settings(request: Request) -> schemas.Settings:
    with unit_of_work(request) as ctx:
        return schemas.Settings(**ctx.settings.model_dump())


@router.put("/settings", response_model=schemas.Settings)
def put_settings(request: Request, body: schemas.SettingsUpdate) -> schemas.Settings:
    state = get_state(request)
    with unit_of_work(request) as ctx:
        updated = update_settings(
            ctx.session,
            ctx.clock,
            ctx.request,
            state.settings_defaults,
            body.model_dump(exclude_unset=True),
        )
        return schemas.Settings(**updated.model_dump())


@router.post("/domains/{name}/expire-now", response_model=schemas.Domain)
def expire_now(request: Request, name: str) -> schemas.Domain:
    with unit_of_work(request) as ctx:
        return to_schema(ctx, LifecycleService(ctx).expire_now(name))


@router.post("/reset", response_model=schemas.ResetResult)
def reset(request: Request, body: schemas.ResetRequest) -> schemas.ResetResult:
    with unit_of_work(request) as ctx:
        result = DomainService(ctx).reset(prefix=body.prefix, everything=body.all)
    get_state(request).resolver.flush(None)
    return schemas.ResetResult(
        deleted_domains=result.deleted_domains, deleted_hosts=result.deleted_hosts
    )


@router.post("/resolver/flush", response_model=schemas.FlushResult)
def flush_resolver(
    request: Request, body: schemas.FlushRequest | None = None
) -> schemas.FlushResult:
    domain = normalize_name(body.domain) if body and body.domain is not None else None
    get_state(request).resolver.flush(domain)
    return schemas.FlushResult(flushed=domain)


@router.post("/publish/reconcile", response_model=schemas.ReconcileResult)
def reconcile(request: Request) -> schemas.ReconcileResult:
    with unit_of_work(request) as ctx:
        fixed = ctx.publisher.reconcile(ctx.session)
    return schemas.ReconcileResult(fixed=fixed)
