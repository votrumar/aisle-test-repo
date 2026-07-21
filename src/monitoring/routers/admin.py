from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from werkzeug.formparser import parse_form_data

from ..db import get_db
from ..models import Sensor
from ..services.config_import import import_alert_rules
from ..services.package_inventory import list_installed_wheels
from ..services.remote_log import register_ssh_key

router = APIRouter(prefix="/admin", tags=["admin"])

_PACKAGES_DIR = Path("/opt/monitoring/packages")
_MAX_SENSOR_CONFIG_BODY_BYTES = 2 * 1024 * 1024
_MAX_SENSOR_CONFIG_FORM_MEMORY_BYTES = 1_048_576
_MAX_SENSOR_CONFIG_FORM_PARTS = 200
_MAX_CONFIG_BODY_BYTES = 1_048_576


async def _read_limited_body(request: Request, max_bytes: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared_size = int(content_length)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid content-length") from exc
        if declared_size < 0:
            raise HTTPException(status_code=400, detail="invalid content-length")
        if declared_size > max_bytes:
            raise HTTPException(status_code=413, detail="request body too large")

    body = bytearray()
    received = 0
    async for chunk in request.stream():
        received += len(chunk)
        if received > max_bytes:
            raise HTTPException(status_code=413, detail="request body too large")
        body.extend(chunk)

    return bytes(body)


@router.post("/register-remote-sensor", status_code=status.HTTP_204_NO_CONTENT)
def register_remote_sensor(payload: dict) -> None:
    try:
        host = payload["host"]
        username = payload["username"]
        private_key_pem = payload["private_key_pem"]
        keyfile_path = payload["keyfile_path"]
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"missing field: {exc.args[0]}")
    if not all(isinstance(v, str) for v in (host, username, private_key_pem, keyfile_path)):
        raise HTTPException(status_code=422, detail="all fields must be strings")
    register_ssh_key(private_key_pem, keyfile_path)


@router.get("/packages")
def list_packages() -> list[dict]:
    if not _PACKAGES_DIR.exists():
        return []
    return list_installed_wheels(_PACKAGES_DIR)


@router.post("/import-sensor-config")
async def import_sensor_config(request: Request, db: Session = Depends(get_db)) -> dict:
    body = await _read_limited_body(request, _MAX_SENSOR_CONFIG_BODY_BYTES)
    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": request.headers.get("content-type", "application/x-www-form-urlencoded"),
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
    }
    _, form, _ = parse_form_data(
        environ,
        max_form_memory_size=_MAX_SENSOR_CONFIG_FORM_MEMORY_BYTES,
        max_form_parts=_MAX_SENSOR_CONFIG_FORM_PARTS,
    )
    accepted = 0
    for name, location in form.items():
        if not name:
            continue
        sensor = Sensor(name=name, location=location or None, metadata_json={})
        db.add(sensor)
        accepted += 1
    db.commit()
    return {"accepted": accepted}


@router.post("/import-config")
async def import_config(request: Request) -> dict:
    yaml_text = (await _read_limited_body(request, _MAX_CONFIG_BODY_BYTES)).decode("utf-8")
    parsed = import_alert_rules(yaml_text)
    return {"parsed": parsed}
