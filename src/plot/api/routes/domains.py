from fastapi import APIRouter, Query, Request, Response

from plot.api import schemas
from plot.api.deps import unit_of_work
from plot.services.context import ServiceContext
from plot.services.domains import (
    DEFAULT_LIST_LIMIT,
    MAX_LIST_LIMIT,
    DomainService,
    DomainView,
    dns_visible,
)

router = APIRouter(prefix="/domains", tags=["domains"])


def to_schema(ctx: ServiceContext, view: DomainView) -> schemas.Domain:
    visible = dns_visible(ctx, view.name)
    return schemas.Domain(
        name=view.name,
        owner=view.owner,
        status=view.status,
        expired=view.expired,
        created_at=view.created_at,
        expires_at=view.expires_at,
        nameservers=view.nameservers,
        overrides=schemas.Overrides(
            propagation_delay=view.overrides.propagation_delay, ns_ttl=view.overrides.ns_ttl
        ),
        dns_visible=schemas.DnsVisible(
            published_at=visible.published_at,
            nameservers=visible.nameservers,
            pending=[schemas.Pending(apply_at=t) for t in visible.pending],
        ),
    )


@router.get("/check", response_model=schemas.DomainCheck, response_model_exclude_none=True)
def check_domain(request: Request, name: str) -> schemas.DomainCheck:
    with unit_of_work(request) as ctx:
        result = DomainService(ctx).check(name)
    return schemas.DomainCheck(name=result.name, available=result.available, reason=result.reason)


@router.post("", status_code=201, response_model=schemas.Domain)
def create_domain(request: Request, body: schemas.DomainCreate) -> schemas.Domain:
    with unit_of_work(request) as ctx:
        view = DomainService(ctx).register(
            body.name, owner=body.owner, years=body.years, nameservers=body.nameservers
        )
        return to_schema(ctx, view)


@router.get("", response_model=schemas.DomainList)
def list_domains(
    request: Request,
    prefix: str | None = None,
    owner: str | None = None,
    limit: int = Query(DEFAULT_LIST_LIMIT, ge=1, le=MAX_LIST_LIMIT),
    cursor: str | None = None,
) -> schemas.DomainList:
    with unit_of_work(request) as ctx:
        page = DomainService(ctx).list_domains(prefix, owner, limit, cursor)
        return schemas.DomainList(
            items=[to_schema(ctx, v) for v in page.items], next_cursor=page.next_cursor
        )


@router.get("/{name}", response_model=schemas.Domain)
def get_domain(request: Request, name: str) -> schemas.Domain:
    with unit_of_work(request) as ctx:
        return to_schema(ctx, DomainService(ctx).get(name))


@router.delete("/{name}", status_code=204)
def delete_domain(request: Request, name: str) -> Response:
    with unit_of_work(request) as ctx:
        DomainService(ctx).delete(name)
    return Response(status_code=204)


@router.post("/{name}/renew", response_model=schemas.Domain)
def renew_domain(request: Request, name: str, body: schemas.RenewRequest) -> schemas.Domain:
    with unit_of_work(request) as ctx:
        return to_schema(ctx, DomainService(ctx).renew(name, body.years))
