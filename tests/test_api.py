from fastapi.testclient import TestClient

from monitoring.main import create_app
from monitoring.services.tokens import sign


def _admin_headers(secret: str) -> dict[str, str]:
    token = sign({"sub": "admin"}, secret)
    return {"Authorization": f"Bearer {token}"}


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


def test_admin_import_config_requires_configured_secret(monkeypatch):
    monkeypatch.delenv("MONITORING_AUTH_SECRET", raising=False)

    with TestClient(create_app()) as admin_client:
        r = admin_client.post("/admin/import-config", content="rules: []")

    assert r.status_code == 503
    assert r.json() == {"detail": "admin auth is not configured"}


def test_admin_import_config_rejects_oversized_body(monkeypatch):
    secret = "test-admin-secret"
    monkeypatch.setenv("MONITORING_AUTH_SECRET", secret)

    with TestClient(create_app()) as admin_client:
        r = admin_client.post(
            "/admin/import-config",
            content="a" * (2 * 1024 * 1024),
            headers=_admin_headers(secret),
        )

    assert r.status_code == 413
    assert r.json() == {"detail": "request body too large"}


def test_admin_import_config_accepts_small_body(monkeypatch):
    secret = "test-admin-secret"
    monkeypatch.setenv("MONITORING_AUTH_SECRET", secret)

    with TestClient(create_app()) as admin_client:
        r = admin_client.post(
            "/admin/import-config",
            content="rules: []",
            headers=_admin_headers(secret),
        )

    assert r.status_code == 200
    assert r.json() == {"parsed": {"rules": []}}


def test_admin_import_sensor_config_rejects_oversized_form(monkeypatch):
    secret = "test-admin-secret"
    monkeypatch.setenv("MONITORING_AUTH_SECRET", secret)

    with TestClient(create_app()) as admin_client:
        r = admin_client.post(
            "/admin/import-sensor-config",
            data={"freezer-9": "z" * (3 * 1024 * 1024)},
            headers=_admin_headers(secret),
        )

    assert r.status_code == 413
    assert r.json() == {"detail": "request body too large"}


def test_admin_import_sensor_config_accepts_small_form(monkeypatch):
    secret = "test-admin-secret"
    monkeypatch.setenv("MONITORING_AUTH_SECRET", secret)

    with TestClient(create_app()) as admin_client:
        r = admin_client.post(
            "/admin/import-sensor-config",
            data={"freezer-9": "warehouse-Z"},
            headers=_admin_headers(secret),
        )

        assert r.status_code == 200
        assert r.json() == {"accepted": 1}

        sensors = admin_client.get("/sensors").json()

    assert len(sensors) == 1
    assert sensors[0]["name"] == "freezer-9"
    assert sensors[0]["location"] == "warehouse-Z"
