import math

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AlertEvent
from ..schemas import AlertEventOut

router = APIRouter(prefix="/alert-events", tags=["alert-events"])


@router.get("", response_model=list[AlertEventOut])
def list_events(
    sensor_id: int | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[AlertEvent]:
    stmt = select(AlertEvent)
    if sensor_id is not None:
        stmt = stmt.where(AlertEvent.sensor_id == sensor_id)
    stmt = stmt.order_by(AlertEvent.triggered_at.desc()).limit(limit)
    return [event for event in db.scalars(stmt).all() if math.isfinite(event.value)]
