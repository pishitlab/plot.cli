"""Error envelope (SPEC §8.1) and request id propagation."""

import logging
import re
import time
import uuid
from typing import Any

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from plot.api.logging import request_id_var
from plot.core.errors import InternalError, PlotError, ValidationFailed

REQUEST_ID_HEADER = "X-Request-ID"
_CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

log = logging.getLogger("plot.api")
access_log = logging.getLogger("plot.access")


def envelope(
    code: str, message: str, details: dict[str, Any], request_id: str | None
) -> dict[str, Any]:
    return {
        "error": {"code": code, "message": message, "details": details},
        "request_id": request_id,
    }


def error_response(request: Request, error: PlotError) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(
        envelope(error.code, error.message, error.details, rid),
        status_code=error.http_status,
        headers={REQUEST_ID_HEADER: rid} if rid else None,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PlotError)
    async def plot_error(request: Request, exc: PlotError) -> JSONResponse:
        return error_response(request, exc)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": list(e.get("loc", ())), "msg": str(e.get("msg", "")), "type": e.get("type")}
            for e in exc.errors()
        ]
        return error_response(request, ValidationFailed(errors=errors))

    @app.middleware("http")
    async def request_context(request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Assign a request id (or keep a well-formed client one) and catch unexpected errors."""
        supplied = request.headers.get(REQUEST_ID_HEADER, "")
        rid = supplied if _CLIENT_REQUEST_ID.match(supplied) else uuid.uuid4().hex
        request.state.request_id = rid
        token = request_id_var.set(rid)
        started = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                log.exception("unhandled error", extra={"request_id": rid})
                response = error_response(request, InternalError())
            response.headers[REQUEST_ID_HEADER] = rid
            # access log: never headers or bodies, so the API key cannot leak (SPEC §15)
            access_log.info(
                "%s %s %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "request_id": rid,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
            return response
        finally:
            request_id_var.reset(token)
