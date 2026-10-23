"""Web UI (SPEC §12.1): Jinja2 pages enhanced with HTMX, mounted at ``/ui``.

Every action goes through the same registrar API as the CLI (``ApiClient``), with the API
key the user typed at login (kept in an HttpOnly cookie). Templates only display data.
"""

from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from plot.cli.client import ApiClient, ApiError
from plot.web import views

HERE = Path(__file__).parent
KEY_COOKIE = "plot_api_key"

ClientFactory = Callable[[str], ApiClient]


class NotLoggedIn(Exception):
    pass


async def form(request: Request) -> dict[str, list[str]]:
    """application/x-www-form-urlencoded body (no python-multipart needed)."""
    return parse_qs((await request.body()).decode(), keep_blank_values=True)


def first(data: dict[str, list[str]], key: str, default: str = "") -> str:
    return (data.get(key) or [default])[0].strip()


def lines(data: dict[str, list[str]], key: str) -> list[str]:
    """Values from a textarea (one per line or comma/space separated)."""
    raw = " ".join(data.get(key, []))
    return [v for v in raw.replace(",", " ").split() if v]


def create_web_app(client_for_key: ClientFactory) -> FastAPI:
    web = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.filters["ago"] = views.relative
    web.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def client(request: Request) -> ApiClient:
        key = request.cookies.get(KEY_COOKIE)
        if not key:
            raise NotLoggedIn
        return client_for_key(key)

    def root(request: Request) -> str:
        # the mount point ("/ui") is the scope's root_path; links work wherever we are mounted
        return f"{str(request.base_url).rstrip('/')}{request.scope.get('root_path', '')}/"

    def page(request: Request, template: str, **context: Any) -> HTMLResponse:
        context["root"] = root(request)
        context.setdefault("error", request.query_params.get("error"))
        context.setdefault("notice", request.query_params.get("notice"))
        return templates.TemplateResponse(request, template, context)

    def back(
        request: Request, path: str = "", *, error: str | None = None, notice: str | None = None
    ) -> RedirectResponse:
        """Redirect to ``path`` under the UI root, carrying a flash message."""
        query = urlencode({k: v for k, v in (("error", error), ("notice", notice)) if v})
        url = root(request) + path
        return RedirectResponse(f"{url}?{query}" if query else url, status_code=303)

    async def act(
        request: Request,
        call: Callable[[ApiClient], Any],
        *,
        then: str,
        notice: str,
        on_error: str | None = None,
    ) -> Response:
        """Run one API call off the event loop, then redirect (POST/redirect/GET)."""
        api = client(request)
        try:
            await run_in_threadpool(call, api)
        except ApiError as err:
            return back(
                request, then if on_error is None else on_error, error=f"{err.code}: {err.message}"
            )
        return back(request, then, notice=notice)

    async def fetch(request: Request, call: Callable[[ApiClient], Any]) -> Any:
        return await run_in_threadpool(call, client(request))

    @web.exception_handler(NotLoggedIn)
    async def login_first(request: Request, exc: NotLoggedIn) -> Response:
        return RedirectResponse(root(request) + "login", status_code=303)

    @web.exception_handler(ApiError)
    async def api_failed(request: Request, exc: ApiError) -> Response:
        if exc.code == "UNAUTHORIZED":
            response = RedirectResponse(root(request) + "login", status_code=303)
            response.delete_cookie(KEY_COOKIE)
            return response
        return page(request, "error.html", error=f"{exc.code}: {exc.message}", status=exc.status)

    # --- login --------------------------------------------------------------------

    @web.get("/login", response_class=HTMLResponse, name="login_page")
    async def login_page(request: Request) -> Response:
        return page(request, "login.html")

    @web.post("/login")
    async def login(request: Request) -> Response:
        key = first(await form(request), "api_key")
        try:
            await run_in_threadpool(client_for_key(key).get, "/admin/settings")
        except ApiError as err:
            return back(request, "login", error=f"{err.code}: {err.message}")
        response = back(request, notice="logged in")
        response.set_cookie(KEY_COOKIE, key, httponly=True, samesite="strict")
        return response

    @web.post("/logout")
    async def logout(request: Request) -> Response:
        response = back(request, "login", notice="logged out")
        response.delete_cookie(KEY_COOKIE)
        return response

    # --- domains ------------------------------------------------------------------

    @web.get("/", response_class=HTMLResponse, name="domains")
    async def domains(request: Request) -> Response:
        prefix = request.query_params.get("prefix") or None
        owner = request.query_params.get("owner") or None
        listing = await fetch(
            request, lambda api: api.get("/domains", prefix=prefix, owner=owner, limit=200)
        )
        return page(
            request,
            "domains.html",
            domains=listing["items"],
            more=listing["next_cursor"],
            prefix=prefix or "",
            owner=owner or "",
        )

    @web.post("/domains")
    async def register(request: Request) -> Response:
        data = await form(request)
        body: dict[str, Any] = {
            "name": first(data, "name"),
            "owner": first(data, "owner", "web") or "web",
            "nameservers": lines(data, "nameservers"),
        }
        if first(data, "years"):
            body["years"] = views.as_int(first(data, "years"))
        name = body["name"]
        return await act(
            request,
            lambda api: api.post("/domains", body),
            then=f"domains/{name}",
            notice=f"registered {name}",
            on_error="",
        )

    return web


def mount_web_ui(app: FastAPI, client_for_key: ClientFactory) -> None:
    app.mount("/ui", create_web_app(client_for_key), name="ui")
