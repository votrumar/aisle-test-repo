from __future__ import annotations

import os
from typing import Iterable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .tokens import verify


_COMMON_WEAK_SECRETS = {
    "change-me",
    "test-secret",
    "dev-secret",
    "secret",
}


def get_auth_secret() -> str:
    """Return the required auth secret.

    No insecure fallback is provided. Additionally, obvious placeholder/weak
    secrets are rejected to reduce the chance of running production with a
    forgeable JWT signing key.
    """

    secret = os.environ.get("MONITORING_AUTH_SECRET")
    if not secret:
        raise RuntimeError("MONITORING_AUTH_SECRET must be set")

    if secret in _COMMON_WEAK_SECRETS or len(secret) < 32:
        raise RuntimeError("MONITORING_AUTH_SECRET is too weak; set a long random value")

    return secret


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
    def __init__(self, app, secret: str) -> None:
        super().__init__(app)
        self._secret = secret

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if _matches_any(path, _PUBLIC_PREFIXES):
            return await call_next(request)

        if not _matches_any(path, _PROTECTED_PREFIXES):
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        scheme, _, token = auth.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return JSONResponse({"detail": "missing bearer token"}, status_code=401)
        try:
            claims = verify(token, self._secret)
        except Exception:
            return JSONResponse({"detail": "invalid token"}, status_code=401)

        if claims.get("role") != "admin":
            return JSONResponse({"detail": "forbidden"}, status_code=403)

        return await call_next(request)


def build_middleware(app) -> PathAuthMiddleware:
    return PathAuthMiddleware(app, secret=get_auth_secret())
