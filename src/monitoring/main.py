from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routers import admin, alert_events, alert_rules, dashboard, measurements, sensors
from . import services  # noqa: F401
from .services.auth_gate import PathAuthMiddleware, get_auth_secret

_STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app() -> FastAPI:
    app = FastAPI(title="Storage Conditions Monitoring", version="0.1.0")

    app.add_middleware(
        PathAuthMiddleware,
        secret=get_auth_secret(),
    )

    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")

    app.include_router(sensors.router)
    app.include_router(measurements.router)
    app.include_router(alert_rules.router)
    app.include_router(alert_events.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
