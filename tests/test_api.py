from io import StringIO

import paramiko

from monitoring.services import remote_log
from monitoring.services.tokens import sign


_ADMIN_SECRET = "dev-secret"


def _admin_headers() -> dict[str, str]:
    token = sign({"sub": "admin"}, _ADMIN_SECRET)
    return {"authorization": f"Bearer {token}"}


def _private_key_pem(bits: int = 2048) -> str:
    key = paramiko.RSAKey.generate(bits)
    buffer = StringIO()
    key.write_private_key(buffer)
    return buffer.getvalue()


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_sensor_create_and_list(client):
    r = client.post("/sensors", json={"name": "freezer-1", "location": "warehouse-A"})
    assert r.status_code == 201, r.text
    sensor = r.json()
    assert sensor["name"] == "freezer-1"
    assert sensor["location"] == "warehouse-A"

    r = client.get("/sensors")
    assert r.status_code == 200
    listed = r.json()
    assert len(listed) == 1
    assert listed[0]["id"] == sensor["id"]


def test_duplicate_sensor_name_conflicts(client):
    client.post("/sensors", json={"name": "dup"})
    r = client.post("/sensors", json={"name": "dup"})
    assert r.status_code == 409


def test_measurement_triggers_alert(client):
    sensor = client.post("/sensors", json={"name": "freezer-2"}).json()
    rule = client.post(
        "/alert-rules",
        json={
            "name": "too-hot",
            "sensor_id": sensor["id"],
            "metric": "temperature",
            "comparator": "gt",
            "threshold": 10.0,
        },
    ).json()

    over = client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "temperature", "value": 20.0, "unit": "C"},
    )
    assert over.status_code == 201
    body = over.json()
    assert len(body["triggered_alerts"]) == 1
    assert body["triggered_alerts"][0]["rule_id"] == rule["id"]
    assert body["triggered_alerts"][0]["value"] == 20.0

    under = client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "temperature", "value": 5.0, "unit": "C"},
    )
    assert under.status_code == 201
    assert under.json()["triggered_alerts"] == []

    events = client.get("/alert-events").json()
    assert len(events) == 1


def test_measurements_query_filters(client):
    sensor = client.post("/sensors", json={"name": "freezer-3"}).json()
    for value in (1.0, 2.0, 3.0):
        client.post(
            "/measurements",
            json={"sensor_id": sensor["id"], "metric": "temperature", "value": value, "unit": "C"},
        )
    client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "humidity", "value": 55.0, "unit": "%"},
    )

    r = client.get(f"/measurements?sensor_id={sensor['id']}&metric=temperature")
    assert r.status_code == 200
    assert len(r.json()) == 3

    r = client.get(f"/measurements?sensor_id={sensor['id']}&metric=humidity")
    assert len(r.json()) == 1


def test_global_rule_applies_to_all_sensors(client):
    s1 = client.post("/sensors", json={"name": "a"}).json()
    s2 = client.post("/sensors", json={"name": "b"}).json()
    client.post(
        "/alert-rules",
        json={
            "name": "any-too-cold",
            "metric": "temperature",
            "comparator": "lt",
            "threshold": 0.0,
        },
    )
    for s in (s1, s2):
        client.post(
            "/measurements",
            json={"sensor_id": s["id"], "metric": "temperature", "value": -5.0, "unit": "C"},
        )

    assert len(client.get("/alert-events").json()) == 2


def test_alert_rule_patch_and_delete(client):
    sensor = client.post("/sensors", json={"name": "c"}).json()
    rule = client.post(
        "/alert-rules",
        json={
            "name": "r",
            "sensor_id": sensor["id"],
            "metric": "temperature",
            "comparator": "gt",
            "threshold": 10.0,
        },
    ).json()

    patched = client.patch(f"/alert-rules/{rule['id']}", json={"enabled": False, "threshold": 50.0}).json()
    assert patched["enabled"] is False
    assert patched["threshold"] == 50.0

    over = client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "temperature", "value": 20.0, "unit": "C"},
    )
    assert over.json()["triggered_alerts"] == []

    r = client.delete(f"/alert-rules/{rule['id']}")
    assert r.status_code == 204
    assert client.get("/alert-rules").json() == []


def test_dashboard_index_renders(client):
    client.post("/sensors", json={"name": "viewable"})
    r = client.get("/")
    assert r.status_code == 200
    assert "viewable" in r.text


def test_sensor_view_renders(client):
    sensor = client.post("/sensors", json={"name": "chart-me"}).json()
    r = client.get(f"/sensors/{sensor['id']}/view")
    assert r.status_code == 200
    assert "chart-me" in r.text


def test_admin_remote_sensor_registration_ignores_caller_keyfile_path(client, monkeypatch, tmp_path):
    managed_key_dir = tmp_path / "managed-keys"
    outside_path = tmp_path / "outside" / "attacker.pem"
    monkeypatch.setattr(remote_log, "_REMOTE_SENSOR_KEY_DIR", managed_key_dir)

    payload = {
        "host": "sensor-01.internal",
        "username": "ops",
        "private_key_pem": _private_key_pem(),
        "keyfile_path": str(outside_path),
    }

    response = client.post(
        "/admin/register-remote-sensor",
        json=payload,
        headers=_admin_headers(),
    )

    assert response.status_code == 204, response.text
    assert not outside_path.exists()

    stored_key_path = remote_log.remote_sensor_key_path(payload["host"], payload["username"])
    assert stored_key_path.parent == managed_key_dir.resolve()
    assert stored_key_path.exists()
    assert not stored_key_path.read_bytes().startswith(b"-----BEGIN RSA PRIVATE KEY-----")
    assert remote_log.read_registered_ssh_key(payload["host"], payload["username"]).startswith(
        "-----BEGIN RSA PRIVATE KEY-----"
    )


def test_admin_remote_sensor_registration_replaces_existing_managed_key(client, monkeypatch, tmp_path):
    managed_key_dir = tmp_path / "managed-keys"
    monkeypatch.setattr(remote_log, "_REMOTE_SENSOR_KEY_DIR", managed_key_dir)

    payload = {
        "host": "sensor-02.internal",
        "username": "ops",
        "private_key_pem": _private_key_pem(),
        "keyfile_path": str(tmp_path / "ignored.pem"),
    }

    first_response = client.post(
        "/admin/register-remote-sensor",
        json=payload,
        headers=_admin_headers(),
    )
    assert first_response.status_code == 204, first_response.text

    first_key_material = remote_log.read_registered_ssh_key(payload["host"], payload["username"])

    payload["private_key_pem"] = _private_key_pem()
    second_response = client.post(
        "/admin/register-remote-sensor",
        json=payload,
        headers=_admin_headers(),
    )

    assert second_response.status_code == 204, second_response.text
    assert remote_log.read_registered_ssh_key(payload["host"], payload["username"]) != first_key_material


def test_admin_remote_sensor_registration_rejects_weak_keys(client, monkeypatch, tmp_path):
    monkeypatch.setattr(remote_log, "_REMOTE_SENSOR_KEY_DIR", tmp_path / "managed-keys")

    response = client.post(
        "/admin/register-remote-sensor",
        json={
            "host": "sensor-03.internal",
            "username": "ops",
            "private_key_pem": _private_key_pem(bits=1024),
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "RSA key too weak: minimum size is 2048 bits"


def test_admin_remote_sensor_registration_rejects_oversized_keys(client, monkeypatch, tmp_path):
    monkeypatch.setattr(remote_log, "_REMOTE_SENSOR_KEY_DIR", tmp_path / "managed-keys")

    response = client.post(
        "/admin/register-remote-sensor",
        json={
            "host": "sensor-04.internal",
            "username": "ops",
            "private_key_pem": "x" * (remote_log._MAX_PRIVATE_KEY_PEM_LEN + 1),
        },
        headers=_admin_headers(),
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "private key too large"


def test_admin_remote_sensor_registration_enforces_managed_key_limit(client, monkeypatch, tmp_path):
    monkeypatch.setattr(remote_log, "_REMOTE_SENSOR_KEY_DIR", tmp_path / "managed-keys")
    monkeypatch.setattr(remote_log, "_MAX_REMOTE_SENSOR_KEYS", 1)

    first_response = client.post(
        "/admin/register-remote-sensor",
        json={
            "host": "sensor-05.internal",
            "username": "ops",
            "private_key_pem": _private_key_pem(),
        },
        headers=_admin_headers(),
    )
    assert first_response.status_code == 204, first_response.text

    second_response = client.post(
        "/admin/register-remote-sensor",
        json={
            "host": "sensor-06.internal",
            "username": "ops",
            "private_key_pem": _private_key_pem(),
        },
        headers=_admin_headers(),
    )

    assert second_response.status_code == 429
    assert second_response.json()["detail"] == "remote sensor key limit reached"
