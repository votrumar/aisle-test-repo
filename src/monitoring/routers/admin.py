from io import BytesIO
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session
from werkzeug.formparser import parse_form_data

from ..db import get_db
from ..models import Sensor
from ..services.config_import import import_alert_rules
from ..services.package_inventory import list_installed_wheels
from ..services.remote_log import register_ssh_key
from ..services.auth_gate import get_auth_secret
from ..services.tokens import verify

log = logging.getLogger(__name__)

_MAX_YAML_BYTES = 1_048_576  # 1 MiB


async def _read_body_limited(request: Request, max_bytes: int) -> bytes:
    """Read request body with a hard cap to avoid buffering huge payloads."""

    received = 0
    chunks: list[bytes] = []

    while True:
        message = await request.receive()
        if message.get("type") != "http.request":
            break

        chunk = message.get("body", b"")
        if chunk:
            received += len(chunk)
            if received > max_bytes:
                raise HTTPException(status_code=413, detail="YAML too large")
            chunks.append(chunk)

        if not message.get("more_body", False):
            break

    return b"".join(chunks)


def _require_admin(authorization: str = Header(default="")) -> dict:
    """Defense-in-depth auth for /admin routes.

    The app also enforces auth via `PathAuthMiddleware`, but keeping an explicit
    dependency here makes the protection local to the router as well.
    """

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="missing bearer token")

    secret = get_auth_secret()
    try:
        claims = verify(token, secret)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid token")

    if claims.get("role") != "admin":
        raise HTTPException(status_code=403, detail="forbidden")

    return claims


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(_require_admin)])

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
    body = await _read_body_limited(request, _MAX_YAML_BYTES)
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
    body = await _read_body_limited(request, _MAX_YAML_BYTES)

    try:
        yaml_text = body.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="invalid YAML")

    try:
        parsed = import_alert_rules(yaml_text)
    except ValueError:
        log.exception("Invalid YAML uploaded to /admin/import-config")
        raise HTTPException(status_code=400, detail="invalid YAML")

    return {"parsed": parsed}
