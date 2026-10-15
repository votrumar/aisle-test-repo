from monitoring.alerts import (
    MAX_GLOBAL_ALERT_RULES_PER_METRIC,
    MAX_RULES_PER_MEASUREMENT,
)
from monitoring.db import SessionLocal
from monitoring.models import AlertRule


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


def test_measurement_and_alert_rule_writes_require_auth(client):
    sensor = client.post("/sensors", json={"name": "secured"}).json()

    measurement = client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "temperature", "value": 20.0, "unit": "C"},
    )
    assert measurement.status_code == 401
    assert measurement.json() == {"detail": "missing bearer token"}

    rule = client.post(
        "/alert-rules",
        json={
            "name": "too-hot",
            "sensor_id": sensor["id"],
            "metric": "temperature",
            "comparator": "gt",
            "threshold": 10.0,
        },
    )
    assert rule.status_code == 401
    assert rule.json() == {"detail": "missing bearer token"}


def test_measurement_triggers_alert(client, auth_headers):
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
        headers=auth_headers,
    ).json()

    over = client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "temperature", "value": 20.0, "unit": "C"},
        headers=auth_headers,
    )
    assert over.status_code == 201
    body = over.json()
    assert len(body["triggered_alerts"]) == 1
    assert body["triggered_alerts"][0]["rule_id"] == rule["id"]
    assert body["triggered_alerts"][0]["value"] == 20.0

    under = client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "temperature", "value": 5.0, "unit": "C"},
        headers=auth_headers,
    )
    assert under.status_code == 201
    assert under.json()["triggered_alerts"] == []

    events = client.get("/alert-events").json()
    assert len(events) == 1


def test_measurements_query_filters(client, auth_headers):
    sensor = client.post("/sensors", json={"name": "freezer-3"}).json()
    for value in (1.0, 2.0, 3.0):
        client.post(
            "/measurements",
            json={"sensor_id": sensor["id"], "metric": "temperature", "value": value, "unit": "C"},
            headers=auth_headers,
        )
    client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "humidity", "value": 55.0, "unit": "%"},
        headers=auth_headers,
    )

    r = client.get(f"/measurements?sensor_id={sensor['id']}&metric=temperature")
    assert r.status_code == 200
    assert len(r.json()) == 3

    r = client.get(f"/measurements?sensor_id={sensor['id']}&metric=humidity")
    assert len(r.json()) == 1


def test_global_rule_applies_to_all_sensors(client, auth_headers):
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
        headers=auth_headers,
    )
    for s in (s1, s2):
        client.post(
            "/measurements",
            json={"sensor_id": s["id"], "metric": "temperature", "value": -5.0, "unit": "C"},
            headers=auth_headers,
        )

    assert len(client.get("/alert-events").json()) == 2


def test_alert_rule_patch_and_delete(client, auth_headers):
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
        headers=auth_headers,
    ).json()

    patched = client.patch(
        f"/alert-rules/{rule['id']}",
        json={"enabled": False, "threshold": 50.0},
        headers=auth_headers,
    ).json()
    assert patched["enabled"] is False
    assert patched["threshold"] == 50.0

    over = client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "temperature", "value": 20.0, "unit": "C"},
        headers=auth_headers,
    )
    assert over.json()["triggered_alerts"] == []

    r = client.delete(f"/alert-rules/{rule['id']}", headers=auth_headers)
    assert r.status_code == 204
    assert client.get("/alert-rules").json() == []


def test_enabled_global_alert_rule_quota_is_enforced(client, auth_headers):
    for idx in range(MAX_GLOBAL_ALERT_RULES_PER_METRIC):
        r = client.post(
            "/alert-rules",
            json={
                "name": f"global-{idx}",
                "metric": "temperature",
                "comparator": "gt",
                "threshold": float(idx),
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text

    rejected = client.post(
        "/alert-rules",
        json={
            "name": "global-overflow",
            "metric": "temperature",
            "comparator": "gt",
            "threshold": 999.0,
        },
        headers=auth_headers,
    )
    assert rejected.status_code == 409
    assert rejected.json() == {
        "detail": "enabled global alert rule limit reached for metric 'temperature'"
    }


def test_measurement_rejects_preexisting_oversized_rule_set(client, auth_headers):
    sensor = client.post("/sensors", json={"name": "legacy-overflow"}).json()

    with SessionLocal() as db:
        db.add_all(
            [
                AlertRule(
                    name=f"legacy-{idx}",
                    metric="temperature",
                    comparator="gt",
                    threshold=-100.0,
                    enabled=True,
                )
                for idx in range(MAX_RULES_PER_MEASUREMENT + 1)
            ]
        )
        db.commit()

    r = client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "temperature", "value": 20.0, "unit": "C"},
        headers=auth_headers,
    )
    assert r.status_code == 503
    assert r.json() == {"detail": "too many enabled alert rules for this measurement"}
    assert client.get(f"/measurements?sensor_id={sensor['id']}").json() == []
    assert client.get("/alert-events").json() == []


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
