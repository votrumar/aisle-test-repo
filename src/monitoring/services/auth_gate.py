from __future__ import annotations

import os
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .tokens import verify


def get_auth_secret() -> str | None:
    secret = os.environ.get("MONITORING_AUTH_SECRET", "").strip()
    return secret or None

_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/healthz",
    "/static",
    "/dashboard",
    "/docs",
    "/openapi.json",
)

_PROTECTED_PREFIXES: tuple[str, ...] = (
    "/admin",
)


def _matches_any(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == p or path.startswith(p + "/") for p in prefixes)


class PathAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, secret: str | None) -> None:
        super().__init__(app)
        self._secret = secret

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if _matches_any(path, _PUBLIC_PREFIXES):
            return await call_next(request)

        if not _matches_any(path, _PROTECTED_PREFIXES):
            return await call_next(request)

        if not self._secret:
            return JSONResponse({"detail": "admin auth is not configured"}, status_code=503)

        auth = request.headers.get("authorization", "")
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse({"detail": "missing bearer token"}, status_code=401)
        try:
            verify(token, self._secret)
        except Exception:
            return JSONResponse({"detail": "invalid token"}, status_code=401)
        return await call_next(request)


def build_middleware(app) -> PathAuthMiddleware:
    return PathAuthMiddleware(app, secret=get_auth_secret())
