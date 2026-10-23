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
from plot.cli.commands.scenario import engine_from_env
from plot.scenarios.engine import Engine, load_catalog
from plot.web import views

HERE = Path(__file__).parent
KEY_COOKIE = "plot_api_key"

ClientFactory = Callable[[str], ApiClient]
EngineFactory = Callable[[ApiClient], Engine]


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


def create_web_app(
    client_for_key: ClientFactory, engine_for: EngineFactory = engine_from_env
) -> FastAPI:
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

    @web.get("/domains/{name}", response_class=HTMLResponse, name="domain")
    async def domain(request: Request, name: str) -> Response:
        data = await fetch(request, lambda api: api.get(f"/domains/{name}"))
        return page(request, "domain.html", d=data, dns=views.dns_panel(data))

    @web.get("/domains/{name}/dns", response_class=HTMLResponse)
    async def domain_dns(request: Request, name: str) -> Response:
        """Fragment polled by HTMX while a change is pending."""
        data = await fetch(request, lambda api: api.get(f"/domains/{name}"))
        return page(request, "_dns_panel.html", d=data, dns=views.dns_panel(data))

    @web.post("/domains/{name}/hold")
    async def hold(request: Request, name: str) -> Response:
        return await act(
            request,
            lambda api: api.put(f"/domains/{name}/status", {"add": ["serverHold"]}),
            then=f"domains/{name}",
            notice="serverHold set",
        )

    @web.post("/domains/{name}/release")
    async def release(request: Request, name: str) -> Response:
        return await act(
            request,
            lambda api: api.put(f"/domains/{name}/status", {"remove": ["serverHold"]}),
            then=f"domains/{name}",
            notice="serverHold removed",
        )

    @web.post("/domains/{name}/renew")
    async def renew(request: Request, name: str) -> Response:
        years = views.as_int(first(await form(request), "years", "1"))
        return await act(
            request,
            lambda api: api.post(f"/domains/{name}/renew", {"years": years}),
            then=f"domains/{name}",
            notice=f"renewed for {years} year(s)",
        )

    @web.post("/domains/{name}/expire-now")
    async def expire_now(request: Request, name: str) -> Response:
        return await act(
            request,
            lambda api: api.post(f"/admin/domains/{name}/expire-now"),
            then=f"domains/{name}",
            notice="expiry moved into the past",
        )

    @web.post("/domains/{name}/overrides")
    async def overrides(request: Request, name: str) -> Response:
        data = await form(request)
        body = views.override_body(first(data, "delay"), first(data, "ttl"))
        return await act(
            request,
            lambda api: api.put(f"/domains/{name}/overrides", body),
            then=f"domains/{name}",
            notice="overrides saved",
        )

    @web.post("/domains/{name}/nameservers")
    async def nameservers(request: Request, name: str) -> Response:
        names = lines(await form(request), "nameservers")
        return await act(
            request,
            lambda api: api.put(f"/domains/{name}/nameservers", {"nameservers": names}),
            then=f"domains/{name}",
            notice="nameservers replaced",
        )

    @web.post("/domains/{name}/delete")
    async def delete(request: Request, name: str) -> Response:
        return await act(
            request,
            lambda api: api.delete(f"/domains/{name}"),
            then="",
            notice=f"deleted {name}",
            on_error=f"domains/{name}",
        )

    # --- hosts --------------------------------------------------------------------

    @web.get("/hosts", response_class=HTMLResponse, name="hosts")
    async def hosts(request: Request) -> Response:
        listing = await fetch(request, lambda api: api.get("/hosts"))
        return page(request, "hosts.html", hosts=listing["items"])

    @web.post("/hosts")
    async def create_host(request: Request) -> Response:
        data = await form(request)
        body = {
            "name": first(data, "name"),
            "ipv4": lines(data, "ipv4"),
            "ipv6": lines(data, "ipv6"),
        }
        return await act(
            request,
            lambda api: api.post("/hosts", body),
            then="hosts",
            notice=f"created {body['name']}",
        )

    @web.post("/hosts/{name}/addresses")
    async def update_host(request: Request, name: str) -> Response:
        data = await form(request)
        body = {"ipv4": lines(data, "ipv4"), "ipv6": lines(data, "ipv6")}
        return await act(
            request,
            lambda api: api.put(f"/hosts/{name}", body),
            then="hosts",
            notice=f"updated {name}",
        )

    @web.post("/hosts/{name}/delete")
    async def delete_host(request: Request, name: str) -> Response:
        return await act(
            request,
            lambda api: api.delete(f"/hosts/{name}"),
            then="hosts",
            notice=f"deleted {name}",
        )

    # --- settings -----------------------------------------------------------------

    @web.get("/settings", response_class=HTMLResponse, name="settings")
    async def settings(request: Request) -> Response:
        current = await fetch(request, lambda api: api.get("/admin/settings"))
        return page(request, "settings.html", s=current)

    @web.post("/settings")
    async def save_settings(request: Request) -> Response:
        data = await form(request)
        body: dict[str, Any] = {
            key: views.as_int(first(data, key))
            for key in ("propagation_delay", "ns_ttl", "default_years", "expiry_grace_days")
            if first(data, key)
        }
        body["flush_on_apply"] = first(data, "flush_on_apply") == "on"
        return await act(
            request,
            lambda api: api.put("/admin/settings", body),
            then="settings",
            notice="settings saved",
        )

    @web.post("/settings/flush")
    async def flush(request: Request) -> Response:
        domain = first(await form(request), "domain") or None
        return await act(
            request,
            lambda api: api.post("/admin/resolver/flush", {"domain": domain}),
            then="settings",
            notice=f"flushed {domain or 'the whole resolver cache'}",
        )

    @web.post("/settings/reset")
    async def reset(request: Request) -> Response:
        data = await form(request)
        prefix = first(data, "prefix")
        body: dict[str, Any] = {"prefix": prefix} if prefix else {"all": first(data, "all") == "on"}
        return await act(
            request,
            lambda api: api.post("/admin/reset", body),
            then="settings",
            notice="reset done",
        )

    # --- history ------------------------------------------------------------------

    @web.get("/history", response_class=HTMLResponse, name="history")
    async def history(request: Request) -> Response:
        name = (request.query_params.get("domain") or "").strip()
        events: list[dict[str, Any]] = []
        error = None
        if name:
            try:
                events = (await fetch(request, lambda api: api.get(f"/domains/{name}/history")))[
                    "items"
                ]
            except ApiError as err:
                error = f"{err.code}: {err.message}"
        else:
            client(request)  # login required
        rows = [views.event_row(e) for e in reversed(events)]
        return page(request, "history.html", domain=name, events=rows, error=error)

    # --- scenarios ----------------------------------------------------------------

    @web.get("/scenarios", response_class=HTMLResponse, name="scenarios")
    async def scenarios(request: Request) -> Response:
        client(request)  # login required
        return page(request, "scenarios.html", catalog=load_catalog().values(), results=None)

    @web.post("/scenarios/run")
    async def run_scenarios(request: Request) -> Response:
        """Run one scenario (``id``) or all; this takes as long as the scenarios do."""
        api = client(request)
        wanted = first(await form(request), "id")
        catalog = load_catalog()
        chosen = (
            list(catalog.values())
            if wanted == "all"
            else [catalog[wanted]]
            if wanted in catalog
            else []
        )
        if not chosen:
            return back(request, "scenarios", error=f"unknown scenario {wanted!r}")
        engine = engine_for(api)
        results = await run_in_threadpool(lambda: [engine.run(s) for s in chosen])
        return page(request, "scenarios.html", catalog=catalog.values(), results=results)

    return web


def mount_web_ui(
    app: FastAPI, client_for_key: ClientFactory, engine_for: EngineFactory = engine_from_env
) -> None:
    app.mount("/ui", create_web_app(client_for_key, engine_for), name="ui")
