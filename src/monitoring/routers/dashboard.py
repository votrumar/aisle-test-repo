from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AlertEvent, Sensor

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

router = APIRouter(tags=["dashboard"], include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    sensors = list(db.scalars(select(Sensor).order_by(Sensor.id)).all())
    recent_alerts = list(
        db.scalars(select(AlertEvent).order_by(AlertEvent.triggered_at.desc()).limit(20)).all()
    )
    return templates.TemplateResponse(
        request,
        "index.html",
        {"sensors": sensors, "recent_alerts": recent_alerts},
    )


@router.get("/sensors/{sensor_id}/view", response_class=HTMLResponse)
def sensor_view(sensor_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    sensor = db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="sensor not found")
    recent_alerts = list(
        db.scalars(
            select(AlertEvent)
            .where(AlertEvent.sensor_id == sensor_id)
            .order_by(AlertEvent.triggered_at.desc())
            .limit(20)
        ).all()
    )
    return templates.TemplateResponse(
        request,
        "sensor.html",
        {"sensor": sensor, "recent_alerts": recent_alerts},
    )
