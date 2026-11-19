from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from aiida.manage import manager
from aiida_gui.app.workchain import router as workchain_router
from aiida_gui.app.task import router as task_router
from aiida_gui.app.process_node import router as process_router
from aiida_gui.app.daemon import router as daemon_router
from aiida_gui.app.data_node import router as datanode_router
from aiida_gui.app.group_node import router as groupnode_router
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException

from pydantic_settings import BaseSettings
from aiida_gui.app.plugin import get_plugins, mount_plugins

# `Host` values accepted by default: the addresses the GUI is served from
# (`cmd_web.py` and `main.py` bind to 127.0.0.1). `0.0.0.0` is accepted
# because `curl http://0.0.0.0:8000` is a common local health check.
# Note: only host names are matched (ports are ignored), and IPv6 literals
# such as `[::1]` are not supported by the underlying middleware.
DEFAULT_ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]


class BackendSettings(BaseSettings):
    """
    Settings can be set by setting the environment variables in upper case.
    For example for setting `aiida_gui_profile` one has to export
    the evironment variable `AIIDA_GUI_PROFILE`.
    """

    aiida_gui_profile: str = ""  # if empty aiida uses default profile
    # Comma-separated list of origins that are allowed to make cross-origin
    # requests to the backend, e.g. "http://localhost:3000". Empty (default)
    # means the backend only accepts same-origin requests.
    aiida_gui_allowed_origins: str = ""
    # Comma-separated list of allowed `Host` header values.
    aiida_gui_allowed_hosts: str = ",".join(DEFAULT_ALLOWED_HOSTS)


backend_settings = BackendSettings()

app = FastAPI()
manager.get_manager().load_profile(backend_settings.aiida_gui_profile)


def _parse_allowed_origins(raw: str) -> list[str]:
    """Parse the comma-separated `AIIDA_GUI_ALLOWED_ORIGINS` setting.

    Entries are normalized to lowercase without a trailing slash. An empty
    setting means no cross-origin requests are allowed.
    """
    return [item.strip().lower().rstrip("/") for item in raw.split(",") if item.strip()]


def _parse_allowed_hosts(raw: str) -> list[str]:
    """Parse the comma-separated `AIIDA_GUI_ALLOWED_HOSTS` setting.

    An explicitly empty setting would make TrustedHostMiddleware reject every
    request, so fall back to the local-only defaults instead.
    """
    hosts = [item.strip().lower() for item in raw.split(",") if item.strip()]
    return hosts or list(DEFAULT_ALLOWED_HOSTS)


_allowed_origins = _parse_allowed_origins(backend_settings.aiida_gui_allowed_origins)
_allowed_hosts = _parse_allowed_hosts(backend_settings.aiida_gui_allowed_hosts)


def _is_origin_allowed(request: Request, origin: str) -> bool:
    """Return whether the `Origin` header is the request's own host or is explicitly allowed."""
    if origin.lower() in _allowed_origins:
        return True
    try:
        origin_netloc = urlsplit(origin).netloc.lower()
    except ValueError:
        return False
    host = request.headers.get("host", "").lower()
    return bool(origin_netloc) and origin_netloc == host


# Only accept requests whose `Host` header is a known local address. This blocks
# DNS-rebinding attacks where an attacker's domain is made to resolve to
# 127.0.0.1 so that the victim's browser treats the API as same-origin.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)

# Cross-origin requests are denied by default. The React frontend is served by
# this same server (same origin) and therefore does not need CORS. If an
# explicit allowlist is configured, only those origins are permitted - never
# the wildcard `*`, and never together with credentials.
if _allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    """Reject cross-site state-changing requests (CSRF).

    Browsers always attach an `Origin` header to cross-site
    POST/PUT/PATCH/DELETE requests. If it is present and does not match this
    host (or an explicitly allowed origin), the request is rejected.
    Non-browser clients (curl, scripts, test clients) send no `Origin` header
    and are unaffected.
    """
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin is not None and not _is_origin_allowed(request, origin):
            return PlainTextResponse("Cross-origin request rejected", status_code=403)
    return await call_next(request)


@app.get("/api", tags=["root"])
async def read_root() -> dict:
    return {"message": "Welcome to AiiDA."}


@app.get("/plugins")
async def list_plugins():
    plugins = get_plugins()
    print(f"Found plugins: {plugins.keys()}")
    plugin_names = [plugin_name for plugin_name in plugins.keys()]
    return {"plugins": plugin_names}


app.include_router(workchain_router)
app.include_router(task_router)
app.include_router(process_router)
app.include_router(datanode_router)
app.include_router(groupnode_router)
app.include_router(daemon_router)
mount_plugins(app)


@app.get("/backend-setting")
async def backend_settings():
    return backend_settings


# Integrating React build into a FastAPI application and serving the build (HTML, CSS, JavaScript) as static files
"""
When navigate to http://127.0.0.1:8000/settings from http://127.0.0.1:8000/ using client-side
routing (i.e., links within your React app), the React Router handles the route /settings
without reloading the page from the server. This is why it works.
However, when you refresh the page at http://127.0.0.1:8000/settings, the browser makes
a request to the FastAPI server for /settings. Since this route isn't defined in FastAPI
(it's a client-side route), the server returns a 404 Not Found error.
so we use the index.html serve all routes except API specific ones, then load all static assets.
"""
backend_dir = Path(__file__).parent
build_dir = backend_dir / "../static"
build_dir = os.getenv("REACT_BUILD_DIR", build_dir)


@app.exception_handler(StarletteHTTPException)
async def _spa_server(req: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return FileResponse(f"{build_dir}/index.html", media_type="text/html")
    else:
        return await http_exception_handler(req, exc)


if os.path.isdir(build_dir):
    app.mount(
        "/static/",
        StaticFiles(directory=build_dir / "static"),
        name="React app static files",
    )

    @app.get("/react-shim.js", include_in_schema=False)
    async def react_shim():
        path = build_dir / "react-shim.js"
        if not path.is_file():
            raise StarletteHTTPException(status_code=404, detail="shim missing")
        return FileResponse(path, media_type="application/javascript")

    @app.get("/react-jsx-runtime-shim.js", include_in_schema=False)
    async def react_jsx_runtime_shim():
        return FileResponse(
            build_dir / "react-jsx-runtime-shim.js", media_type="application/javascript"
        )

    @app.get("/react-router-dom-shim.js", include_in_schema=False)
    async def react_router_dom_shim():
        path = build_dir / "react-router-dom-shim.js"
        if not path.is_file():
            raise StarletteHTTPException(status_code=404, detail="shim missing")
        return FileResponse(path, media_type="application/javascript")

    @app.get("/use-sync-external-store-shim.js", include_in_schema=False)
    async def use_sync_external_store_shim():
        path = build_dir / "use-sync-external-store-shim.js"
        if not path.is_file():
            raise StarletteHTTPException(status_code=404, detail="shim missing")
        return FileResponse(path, media_type="application/javascript")
