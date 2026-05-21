from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Sensor
from ..schemas import SensorCreate, SensorOut

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.post("", response_model=SensorOut, status_code=status.HTTP_201_CREATED)
def create_sensor(payload: SensorCreate, db: Session = Depends(get_db)) -> Sensor:
    sensor = Sensor(name=payload.name, location=payload.location)
    db.add(sensor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"sensor name {payload.name!r} already exists")
    db.refresh(sensor)
    return sensor


@router.get("", response_model=list[SensorOut])
def list_sensors(db: Session = Depends(get_db)) -> list[Sensor]:
    return list(db.scalars(select(Sensor).order_by(Sensor.id)).all())


@router.get("/{sensor_id}", response_model=SensorOut)
def get_sensor(sensor_id: int, db: Session = Depends(get_db)) -> Sensor:
    sensor = db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="sensor not found")
    return sensor
