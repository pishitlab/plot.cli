from dataclasses import asdict

from fastapi import APIRouter, Request, Response

from plot.api import schemas
from plot.api.deps import unit_of_work
from plot.services.hosts import HostService, HostView

router = APIRouter(prefix="/hosts", tags=["hosts"])


def to_schema(view: HostView) -> schemas.Host:
    return schemas.Host(**asdict(view))


@router.post("", status_code=201, response_model=schemas.Host)
def create_host(request: Request, body: schemas.HostCreate) -> schemas.Host:
    with unit_of_work(request) as ctx:
        return to_schema(HostService(ctx).create(body.name, ipv4=body.ipv4, ipv6=body.ipv6))


@router.get("", response_model=schemas.HostList)
def list_hosts(request: Request) -> schemas.HostList:
    with unit_of_work(request) as ctx:
        return schemas.HostList(items=[to_schema(v) for v in HostService(ctx).list_hosts()])


@router.get("/{name}", response_model=schemas.Host)
def get_host(request: Request, name: str) -> schemas.Host:
    with unit_of_work(request) as ctx:
        return to_schema(HostService(ctx).get(name))


@router.put("/{name}", response_model=schemas.Host)
def update_host(request: Request, name: str, body: schemas.HostUpdate) -> schemas.Host:
    with unit_of_work(request) as ctx:
        return to_schema(HostService(ctx).update(name, ipv4=body.ipv4, ipv6=body.ipv6))


@router.delete("/{name}", status_code=204)
def delete_host(request: Request, name: str) -> Response:
    with unit_of_work(request) as ctx:
        HostService(ctx).delete(name)
    return Response(status_code=204)
