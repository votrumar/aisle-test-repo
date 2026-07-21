from sqlalchemy import create_engine, text

from monitoring.config import settings


def _json_headers() -> dict[str, str]:
    return {"content-type": "application/json"}


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


def test_alert_rule_threshold_must_be_finite(client):
    for threshold_literal in ("NaN", "Infinity", "-Infinity"):
        created = client.post(
            "/alert-rules",
            content=(
                "{"
                f'"name":"bad-{threshold_literal}",'
                '"metric":"temperature",'
                '"comparator":"gt",'
                f'"threshold":{threshold_literal}'
                "}"
            ),
            headers=_json_headers(),
        )
        assert created.status_code == 422, created.text

    rule = client.post(
        "/alert-rules",
        json={
            "name": "finite-only",
            "metric": "temperature",
            "comparator": "gt",
            "threshold": 10.0,
        },
    ).json()

    for threshold_literal in ("NaN", "Infinity", "-Infinity"):
        patched = client.patch(
            f"/alert-rules/{rule['id']}",
            content=f'{{"threshold":{threshold_literal}}}',
            headers=_json_headers(),
        )
        assert patched.status_code == 422, patched.text



def test_legacy_non_finite_rules_are_hidden_and_skipped(client):
    sensor = client.post("/sensors", json={"name": "legacy-rule-sensor"}).json()
    valid_rule = client.post(
        "/alert-rules",
        json={
            "name": "real-threshold",
            "metric": "temperature",
            "comparator": "gt",
            "threshold": 10.0,
        },
    ).json()

    engine = create_engine(settings.database_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE alert_rules DROP CONSTRAINT IF EXISTS alert_rules_threshold_finite_chk"))
        legacy_rule_id = conn.execute(
            text(
                """
                INSERT INTO alert_rules (name, metric, comparator, threshold, enabled)
                VALUES ('legacy-nan', 'temperature', 'gt', CAST('NaN' AS DOUBLE PRECISION), TRUE)
                RETURNING id
                """
            )
        ).scalar_one()
        conn.execute(
            text(
                """
                ALTER TABLE alert_rules
                ADD CONSTRAINT alert_rules_threshold_finite_chk
                CHECK (threshold::TEXT NOT IN ('NaN', 'Infinity', '-Infinity')) NOT VALID
                """
            )
        )
    engine.dispose()

    listed = client.get("/alert-rules")
    assert listed.status_code == 200, listed.text
    assert listed.json() == [valid_rule]

    measurement = client.post(
        "/measurements",
        json={"sensor_id": sensor["id"], "metric": "temperature", "value": 20.0, "unit": "C"},
    )
    assert measurement.status_code == 201, measurement.text
    triggered = measurement.json()["triggered_alerts"]
    assert [event["rule_id"] for event in triggered] == [valid_rule["id"]]

    blocked_patch = client.patch(f"/alert-rules/{legacy_rule_id}", json={"enabled": False})
    assert blocked_patch.status_code == 409, blocked_patch.text

    repaired = client.patch(f"/alert-rules/{legacy_rule_id}", json={"threshold": 30.0, "enabled": False})
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["threshold"] == 30.0



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
