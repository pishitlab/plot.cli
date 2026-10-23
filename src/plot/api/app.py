"""FastAPI application factory (SPEC §8)."""

import uuid

from fastapi import APIRouter, Depends, FastAPI, Request, Response
from starlette.middleware.base import RequestResponseEndpoint

from plot import __version__
from plot.api.deps import AppState, require_api_key
from plot.api.errors import install_error_handlers
from plot.api.routes import health

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

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.request_id = uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    public = APIRouter(prefix=API_PREFIX)
    public.include_router(health.router)
    protected = APIRouter(prefix=API_PREFIX, dependencies=[Depends(require_api_key)])
    app.include_router(public)
    app.include_router(protected)
    return app
