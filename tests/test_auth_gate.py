import asyncio

from starlette.responses import JSONResponse

from monitoring.services.auth_gate import PathAuthMiddleware


class _DummyURL:
    def __init__(self, path: str) -> None:
        self.path = path


class _DummyRequest:
    def __init__(self, *, scope_path: str, url_path: str, headers: dict[str, str] | None = None) -> None:
        # Match the pieces of the Starlette Request interface used by PathAuthMiddleware.
        self.scope = {"path": scope_path}
        self.url = _DummyURL(url_path)
        self.headers = headers or {}


async def _dummy_app(scope, receive, send) -> None:  # pragma: no cover
    raise RuntimeError("not used by these unit tests")


def test_admin_auth_gate_uses_scope_path_not_url_path() -> None:
    """Regression: auth gating must not be influenced by a malformed Host header.

    The middleware should use the raw ASGI scope path for decisions, not request.url.path.
    """

    middleware = PathAuthMiddleware(_dummy_app, secret="dev-secret")

    async def call_next(_request):
        return JSONResponse({"ok": True}, status_code=200)

    # Simulate the vulnerable condition: the raw ASGI path is under /admin,
    # but request.url.path has been desynced (e.g., via malformed Host parsing).
    request = _DummyRequest(scope_path="/admin/packages", url_path="/packages")

    response = asyncio.run(middleware.dispatch(request, call_next))
    assert response.status_code == 401


def test_non_admin_path_not_blocked_even_if_url_path_looks_admin() -> None:
    middleware = PathAuthMiddleware(_dummy_app, secret="dev-secret")

    async def call_next(_request):
        return JSONResponse({"ok": True}, status_code=200)

    request = _DummyRequest(scope_path="/sensors", url_path="/admin/sensors")

    response = asyncio.run(middleware.dispatch(request, call_next))
    assert response.status_code == 200
