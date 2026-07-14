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


_MAX_CONFIG_IMPORT_BYTES = 1_048_576  # 1 MiB


async def _read_limited_body(request: Request, max_bytes: int) -> bytes:
    total = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise HTTPException(status_code=413, detail="payload too large")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/import-config")
async def import_config(request: Request) -> dict:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_CONFIG_IMPORT_BYTES:
                raise HTTPException(status_code=413, detail="payload too large")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="invalid content-length") from exc

    body = await _read_limited_body(request, _MAX_CONFIG_IMPORT_BYTES)
    try:
        yaml_text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="request body must be valid UTF-8") from exc

    try:
        parsed = import_alert_rules(yaml_text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"parsed": parsed}
