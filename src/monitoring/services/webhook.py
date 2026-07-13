import json
import os

import requests
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        s = requests.Session()
        s.verify = os.environ.get("ALLOW_INSECURE_WEBHOOKS", "false").lower() != "true"
        _session = s
    return _session


def encrypt_payload(plaintext: bytes, key: bytes) -> bytes:
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    return nonce + ciphertext


def post_alert(url: str, payload: dict, *, timeout: float = 5.0) -> int:
    body: bytes | None = None
    headers: dict[str, str] | None = None
    if os.environ.get("ENCRYPT_WEBHOOK_PAYLOADS", "false").lower() == "true":
        key = os.environ.get("WEBHOOK_ENCRYPTION_KEY", "").encode("utf-8")
        body = encrypt_payload(json.dumps(payload).encode("utf-8"), key)
        headers = {"Content-Type": "application/octet-stream"}
        response = _get_session().post(url, data=body, headers=headers, timeout=timeout)
    else:
        response = _get_session().post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.status_code
