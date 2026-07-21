import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

_DEFAULT_DB = "postgresql+psycopg://monitoring:monitoring@localhost:5432/monitoring"
_DEFAULT_REMOTE_SENSOR_KEY_ENCRYPTION_SECRET = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="
os.environ.setdefault("DATABASE_URL", _DEFAULT_DB)
os.environ.setdefault(
    "REMOTE_SENSOR_KEY_ENCRYPTION_SECRET",
    _DEFAULT_REMOTE_SENSOR_KEY_ENCRYPTION_SECRET,
)

from monitoring.config import settings  # noqa: E402  (imported after env var)
from monitoring.main import app  # noqa: E402

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
