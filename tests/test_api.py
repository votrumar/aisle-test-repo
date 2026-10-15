from io import StringIO

import paramiko

from monitoring.services import remote_log, tokens


def _admin_headers() -> dict[str, str]:
    token = tokens.sign({"sub": "admin", "role": "admin"}, "dev-secret")
    return {"authorization": f"Bearer {token}"}


def _user_headers() -> dict[str, str]:
    token = tokens.sign({"sub": "user", "role": "viewer"}, "dev-secret")
    return {"authorization": f"Bearer {token}"}


def _private_key_pem() -> str:
    key = paramiko.RSAKey.generate(1024)
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


def test_register_remote_sensor_stores_key_in_confined_dir(client, monkeypatch, tmp_path):
    key_dir = tmp_path / "remote-sensor-keys"
    monkeypatch.setattr(remote_log, "_REMOTE_SENSOR_KEYS_DIR", key_dir)

    payload = {
        "host": "sensor-1.example.com",
        "username": "monitor",
        "private_key_pem": _private_key_pem(),
        "keyfile_path": "sensor-1/id_rsa",
    }

    r = client.post("/admin/register-remote-sensor", json=payload, headers=_admin_headers())
    assert r.status_code == 204, r.text

    written = key_dir / "sensor-1" / "id_rsa"
    assert written.exists()
    original = written.read_text()
    assert "BEGIN RSA PRIVATE KEY" in original

    duplicate = client.post("/admin/register-remote-sensor", json=payload, headers=_admin_headers())
    assert duplicate.status_code == 409
    assert written.read_text() == original


def test_register_remote_sensor_rejects_escape_paths(client, monkeypatch, tmp_path):
    key_dir = tmp_path / "remote-sensor-keys"
    monkeypatch.setattr(remote_log, "_REMOTE_SENSOR_KEYS_DIR", key_dir)
    outside = tmp_path / "escape.pem"

    for attempted_path in (str(outside), "../escape.pem"):
        payload = {
            "host": "sensor-1.example.com",
            "username": "monitor",
            "private_key_pem": _private_key_pem(),
            "keyfile_path": attempted_path,
        }

        r = client.post("/admin/register-remote-sensor", json=payload, headers=_admin_headers())
        assert r.status_code == 422
        assert r.json()["detail"].startswith("keyfile_path")

    assert not outside.exists()
    assert not key_dir.exists()


def test_register_remote_sensor_requires_admin_role(client):
    payload = {
        "host": "sensor-1.example.com",
        "username": "monitor",
        "private_key_pem": _private_key_pem(),
        "keyfile_path": "sensor-1/id_rsa",
    }

    r = client.post("/admin/register-remote-sensor", json=payload, headers=_user_headers())
    assert r.status_code == 403
    assert r.json() == {"detail": "admin role required"}


def test_register_remote_sensor_rejects_oversized_private_key(client, monkeypatch, tmp_path):
    key_dir = tmp_path / "remote-sensor-keys"
    monkeypatch.setattr(remote_log, "_REMOTE_SENSOR_KEYS_DIR", key_dir)

    payload = {
        "host": "sensor-1.example.com",
        "username": "monitor",
        "private_key_pem": "A" * 16_385,
        "keyfile_path": "sensor-1/id_rsa",
    }

    r = client.post("/admin/register-remote-sensor", json=payload, headers=_admin_headers())
    assert r.status_code == 413
    assert r.json() == {"detail": "private_key_pem too large"}
    assert not key_dir.exists()


def test_register_remote_sensor_rejects_deep_key_paths(client, monkeypatch, tmp_path):
    key_dir = tmp_path / "remote-sensor-keys"
    monkeypatch.setattr(remote_log, "_REMOTE_SENSOR_KEYS_DIR", key_dir)

    payload = {
        "host": "sensor-1.example.com",
        "username": "monitor",
        "private_key_pem": _private_key_pem(),
        "keyfile_path": "/".join(["nested"] * 9),
    }

    r = client.post("/admin/register-remote-sensor", json=payload, headers=_admin_headers())
    assert r.status_code == 422
    assert r.json() == {"detail": "keyfile_path too deep"}
    assert not key_dir.exists()
