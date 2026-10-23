"""Error envelope (SPEC §8.1)."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from plot.core.errors import PlotError


def envelope(
    code: str, message: str, details: dict[str, Any], request_id: str | None
) -> dict[str, Any]:
    return {
        "error": {"code": code, "message": message, "details": details},
        "request_id": request_id,
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(PlotError)
    async def plot_error(request: Request, exc: PlotError) -> JSONResponse:
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            envelope(exc.code, exc.message, exc.details, rid), status_code=exc.http_status
        )
