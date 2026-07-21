from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..alerts import evaluate_measurement
from ..config import get_settings
from ..db import get_db
from ..models import Measurement, Sensor
from ..schemas import MeasurementCreate, MeasurementOut, MeasurementResponse
from ..services import tokens

router = APIRouter(prefix="/measurements", tags=["measurements"])

_measurement_bearer = HTTPBearer(auto_error=False)


def _require_device_claims(
    credentials: HTTPAuthorizationCredentials | None = Depends(_measurement_bearer),
) -> dict:
    if credentials is None:
        raise HTTPException(status_code=401, detail="missing bearer token")

    settings = get_settings()
    try:
        return tokens.verify(credentials.credentials, settings.jwt_secret.get_secret_value())
    except Exception:
        raise HTTPException(status_code=401, detail="invalid device token")


@router.post("", response_model=MeasurementResponse, status_code=status.HTTP_201_CREATED)
def create_measurement(
    payload: MeasurementCreate,
    device_claims: dict = Depends(_require_device_claims),
    db: Session = Depends(get_db),
) -> MeasurementResponse:
    sensor = db.get(Sensor, payload.sensor_id)

    authorized_sensor_id = device_claims.get("sensor_id")
    if isinstance(authorized_sensor_id, str):
        try:
            authorized_sensor_id = int(authorized_sensor_id)
        except ValueError:
            authorized_sensor_id = None

    authorized_sensor_name = device_claims.get("sensor_name")
    if sensor is None or (
        authorized_sensor_id != sensor.id and authorized_sensor_name != sensor.name
    ):
        raise HTTPException(status_code=404, detail="sensor not found")

    measurement = Measurement(
        sensor_id=sensor.id,
        metric=payload.metric,
        value=payload.value,
        unit=payload.unit,
    )
    if payload.recorded_at is not None:
        measurement.recorded_at = payload.recorded_at

    db.add(measurement)
    db.flush()

    events = evaluate_measurement(db, measurement)
    db.commit()
    db.refresh(measurement)
    for ev in events:
        db.refresh(ev)

    return MeasurementResponse(measurement=measurement, triggered_alerts=events)  # type: ignore[arg-type]


@router.get("", response_model=list[MeasurementOut])
def list_measurements(
    sensor_id: int | None = None,
    metric: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    limit: int = Query(500, ge=1, le=10_000),
    db: Session = Depends(get_db),
) -> list[Measurement]:
    stmt = select(Measurement)
    if sensor_id is not None:
        stmt = stmt.where(Measurement.sensor_id == sensor_id)
    if metric is not None:
        stmt = stmt.where(Measurement.metric == metric)
    if since is not None:
        stmt = stmt.where(Measurement.recorded_at >= since)
    if until is not None:
        stmt = stmt.where(Measurement.recorded_at <= until)
    stmt = stmt.order_by(Measurement.recorded_at.desc()).limit(limit)
    return list(db.scalars(stmt).all())
