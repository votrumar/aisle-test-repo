import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

_DEFAULT_DB = "postgresql+psycopg://monitoring:monitoring@localhost:5432/monitoring"
os.environ.setdefault("DATABASE_URL", _DEFAULT_DB)
os.environ.setdefault("MONITORING_AUTH_SECRET", "test-auth-secret")

from monitoring.config import settings  # noqa: E402  (imported after env var)
from monitoring.main import app  # noqa: E402
from monitoring.services.tokens import sign  # noqa: E402

_INIT_SQL = Path(__file__).resolve().parent.parent / "scripts" / "init.sql"
_TABLES = ("alert_events", "alert_rules", "measurements", "sensors")


def _truncate_all(engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
        )


@pytest.fixture(scope="session", autouse=True)
def _bootstrap_db():
    engine = create_engine(settings.database_url, future=True)
    with engine.begin() as conn:
        conn.execute(text(_INIT_SQL.read_text()))
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def _clean_db():
    engine = create_engine(settings.database_url, future=True)
    _truncate_all(engine)
    engine.dispose()
    yield


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    token = sign({"sub": "pytest"}, os.environ["MONITORING_AUTH_SECRET"])
    return {"authorization": f"Bearer {token}"}
