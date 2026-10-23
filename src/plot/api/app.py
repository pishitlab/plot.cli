"""FastAPI application factory (SPEC §8)."""

from fastapi import APIRouter, Depends, FastAPI

from plot import __version__
from plot.api.deps import AppState, require_api_key
from plot.api.errors import install_error_handlers
from plot.api.routes import domains, health

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
    protected = APIRouter(prefix=API_PREFIX, dependencies=[Depends(require_api_key)])
    protected.include_router(domains.router)
    app.include_router(public)
    app.include_router(protected)
    return app
