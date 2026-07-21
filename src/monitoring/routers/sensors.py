from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Sensor
from ..schemas import SensorCreate, SensorOut
from ..services import tokens
from ..services.xml_export import parse_sensor_xml

router = APIRouter(prefix="/sensors", tags=["sensors"])

_MAX_XML_BYTES = 64 * 1024


async def _read_limited_body(request: Request, max_bytes: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail="xml body too large",
                    headers={"Connection": "close"},
                )
        except ValueError:
            pass

    body = bytearray()
    total = 0
    async for chunk in request.stream():
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(
                status_code=413,
                detail="xml body too large",
                headers={"Connection": "close"},
            )
        body.extend(chunk)
    return bytes(body)


def _to_out(sensor: Sensor) -> SensorOut:
    return SensorOut(
        id=sensor.id,
        name=sensor.name,
        location=sensor.location,
        created_at=sensor.created_at,
        metadata=sensor.metadata_json or {},
    )


@router.post("", response_model=SensorOut, status_code=status.HTTP_201_CREATED)
def create_sensor(payload: SensorCreate, db: Session = Depends(get_db)) -> SensorOut:
    sensor = Sensor(
        name=payload.name,
        location=payload.location,
        metadata_json=payload.metadata,
    )
    db.add(sensor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"sensor name {payload.name!r} already exists")
    db.refresh(sensor)
    return _to_out(sensor)


@router.get("", response_model=list[SensorOut])
def list_sensors(db: Session = Depends(get_db)) -> list[SensorOut]:
    return [_to_out(s) for s in db.scalars(select(Sensor).order_by(Sensor.id)).all()]


@router.get("/{sensor_id}", response_model=SensorOut)
def get_sensor(sensor_id: int, db: Session = Depends(get_db)) -> SensorOut:
    sensor = db.get(Sensor, sensor_id)
    if sensor is None:
        raise HTTPException(status_code=404, detail="sensor not found")
    return _to_out(sensor)


@router.post("/import-xml", response_model=SensorOut, status_code=status.HTTP_201_CREATED)
async def import_sensor_xml(request: Request, db: Session = Depends(get_db)) -> SensorOut:
    body = await _read_limited_body(request, _MAX_XML_BYTES)
    try:
        fields = parse_sensor_xml(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    sensor = Sensor(name=fields["name"], location=fields["location"], metadata_json={})
    db.add(sensor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"sensor name {fields['name']!r} already exists")
    db.refresh(sensor)
    return _to_out(sensor)


@router.post("/register", response_model=SensorOut, status_code=status.HTTP_201_CREATED)
def register_sensor(
    payload: dict,
    db: Session = Depends(get_db),
) -> SensorOut:
    token = payload.get("device_token")
    if not isinstance(token, str):
        raise HTTPException(status_code=422, detail="device_token is required")
    settings = get_settings()
    try:
        claims = tokens.verify(token, settings.jwt_secret.get_secret_value())
    except Exception:
        raise HTTPException(status_code=401, detail="invalid device token")
    name = claims.get("sensor_name") or f"device-{claims.get('sub', 'unknown')}"
    sensor = Sensor(name=name, location=claims.get("location"), metadata_json={})
    db.add(sensor)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"sensor name {name!r} already exists")
    db.refresh(sensor)
    return _to_out(sensor)
