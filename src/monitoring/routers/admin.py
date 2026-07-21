from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from werkzeug.formparser import parse_form_data

from ..db import get_db
from ..models import Sensor
from ..services.config_import import import_alert_rules
from ..services.package_inventory import list_installed_wheels
from ..services.remote_log import RemoteSensorKeyError, register_ssh_key

router = APIRouter(prefix="/admin", tags=["admin"])

_PACKAGES_DIR = Path("/opt/monitoring/packages")


@router.post("/register-remote-sensor", status_code=status.HTTP_204_NO_CONTENT)
def register_remote_sensor(payload: dict) -> None:
    try:
        host = payload["host"]
        username = payload["username"]
        private_key_pem = payload["private_key_pem"]
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"missing field: {exc.args[0]}")
    if not all(isinstance(v, str) for v in (host, username, private_key_pem)):
        raise HTTPException(status_code=422, detail="all fields must be strings")
    try:
        register_ssh_key(private_key_pem, host, username)
    except RemoteSensorKeyError as exc:
        detail = exc.detail if exc.status_code < 500 else "remote sensor key storage is unavailable"
        raise HTTPException(status_code=exc.status_code, detail=detail) from exc


@router.get("/packages")
def list_packages() -> list[dict]:
    if not _PACKAGES_DIR.exists():
        return []
    return list_installed_wheels(_PACKAGES_DIR)


@router.post("/import-sensor-config")
async def import_sensor_config(request: Request, db: Session = Depends(get_db)) -> dict:
    body = await request.body()
    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": request.headers.get("content-type", "application/x-www-form-urlencoded"),
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
    }
    _, form, _ = parse_form_data(environ, max_form_memory_size=1_048_576, max_form_parts=200)
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
    yaml_text = (await request.body()).decode("utf-8")
    parsed = import_alert_rules(yaml_text)
    return {"parsed": parsed}
