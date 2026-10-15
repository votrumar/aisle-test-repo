from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..alerts import evaluate_measurement
from ..db import get_db
from ..models import Measurement, Sensor
from ..schemas import MeasurementCreate, MeasurementOut, MeasurementResponse

router = APIRouter(prefix="/measurements", tags=["measurements"])


@router.post("", response_model=MeasurementResponse, status_code=status.HTTP_201_CREATED)
def create_measurement(payload: MeasurementCreate, db: Session = Depends(get_db)) -> MeasurementResponse:
    if db.get(Sensor, payload.sensor_id) is None:
        raise HTTPException(status_code=404, detail=f"sensor {payload.sensor_id} not found")

    measurement = Measurement(
        sensor_id=payload.sensor_id,
        metric=payload.metric,
        value=payload.value,
        unit=payload.unit,
    )
    if payload.recorded_at is not None:
        measurement.recorded_at = payload.recorded_at

    db.add(measurement)
    db.flush()

    try:
        events = evaluate_measurement(db, measurement)
        db.commit()
    except Exception:
        db.rollback()
        raise
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
