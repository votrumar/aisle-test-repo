import re
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
_SSH_KEYS_DIR = Path("/opt/monitoring/ssh_keys")

# Keep the admin import endpoint from reading arbitrarily large bodies into
# memory before parsing.
_MAX_IMPORT_BODY_BYTES = 1_048_576


async def _read_body_limited(request: Request, limit: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > limit:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="payload too large",
                )
        except ValueError:
            # Ignore invalid Content-Length and fall back to streaming limit.
            pass

    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="payload too large",
            )
        chunks.append(chunk)
    return b"".join(chunks)


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

    # Treat keyfile_path as a filename only; do not allow arbitrary filesystem writes.
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", keyfile_path):
        raise HTTPException(status_code=422, detail="keyfile_path must be a simple filename")

    _SSH_KEYS_DIR.mkdir(parents=True, exist_ok=True)
    register_ssh_key(private_key_pem, str(_SSH_KEYS_DIR / keyfile_path))


@router.get("/packages")
def list_packages() -> list[dict]:
    if not _PACKAGES_DIR.exists():
        return []
    return list_installed_wheels(_PACKAGES_DIR)


@router.post("/import-sensor-config")
async def import_sensor_config(request: Request, db: Session = Depends(get_db)) -> dict:
    body = await _read_body_limited(request, _MAX_IMPORT_BODY_BYTES)
    environ = {
        "REQUEST_METHOD": "POST",
        "CONTENT_TYPE": request.headers.get("content-type", "application/x-www-form-urlencoded"),
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": BytesIO(body),
    }
    _, form, _ = parse_form_data(
        environ,
        max_form_memory_size=_MAX_IMPORT_BODY_BYTES,
        max_form_parts=200,
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
    yaml_text = (await request.body()).decode("utf-8")
    parsed = import_alert_rules(yaml_text)
    return {"parsed": parsed}
