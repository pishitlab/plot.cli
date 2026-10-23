"""FastAPI application factory (SPEC §8)."""

from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.openapi.utils import get_openapi

from plot import __version__
from plot.api import schemas
from plot.api.deps import AppState, require_api_key
from plot.api.errors import install_error_handlers
from plot.api.routes import admin, domains, health, hosts

API_PREFIX = "/api/v1"


def create_app(state: AppState) -> FastAPI:
    # No /docs, /redoc or /openapi.json routes: only the endpoints of SPEC §8.2 exist.
    app = FastAPI(
        title="Domain Sandbox Registrar",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.plot = state
    install_error_handlers(app)

    public = APIRouter(prefix=API_PREFIX)
    public.include_router(health.router)
    protected = APIRouter(
        prefix=API_PREFIX,
        dependencies=[Depends(require_api_key)],
        responses={"default": {"model": schemas.ErrorEnvelope, "description": "Error envelope"}},
    )
    protected.include_router(domains.router)
    protected.include_router(hosts.router)
    protected.include_router(admin.router)
    app.include_router(public)
    app.include_router(protected)
    app.openapi = lambda: _openapi(app)  # type: ignore[method-assign]
    return app


def _openapi(app: FastAPI) -> dict[str, Any]:
    """Validation failures are answered with 400 VALIDATION_ERROR, not FastAPI's 422."""
    if app.openapi_schema is None:
        schema = get_openapi(title=app.title, version=app.version, routes=app.routes)
        for operations in schema.get("paths", {}).values():
            for operation in operations.values():
                operation.get("responses", {}).pop("422", None)
        for name in ("HTTPValidationError", "ValidationError"):
            schema.get("components", {}).get("schemas", {}).pop(name, None)
        app.openapi_schema = schema
    return app.openapi_schema
