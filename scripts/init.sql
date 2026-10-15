-- Storage monitoring schema. Re-runnable: every object is IF NOT EXISTS so
-- the script is safe to apply against an existing database. The Postgres
-- container runs this from /docker-entrypoint-initdb.d/ on first boot.

CREATE TABLE IF NOT EXISTS sensors (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,
    location      TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Keep existing databases compatible if the column was added after initial boot.
ALTER TABLE sensors
    ADD COLUMN IF NOT EXISTS metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS measurements (
    id           BIGSERIAL PRIMARY KEY,
    sensor_id    INTEGER NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    metric       TEXT NOT NULL,
    value        DOUBLE PRECISION NOT NULL,
    unit         TEXT NOT NULL,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_measurements_sensor_time
    ON measurements (sensor_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS ix_measurements_metric_time
    ON measurements (metric, recorded_at DESC);

CREATE TABLE IF NOT EXISTS alert_rules (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    sensor_id   INTEGER REFERENCES sensors(id) ON DELETE CASCADE,
    metric      TEXT NOT NULL,
    comparator  TEXT NOT NULL CHECK (comparator IN ('gt', 'gte', 'lt', 'lte')),
    threshold   DOUBLE PRECISION NOT NULL,
    enabled     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS alert_events (
    id              BIGSERIAL PRIMARY KEY,
    rule_id         INTEGER NOT NULL REFERENCES alert_rules(id) ON DELETE CASCADE,
    measurement_id  BIGINT NOT NULL REFERENCES measurements(id) ON DELETE CASCADE,
    sensor_id       INTEGER NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
    value           DOUBLE PRECISION NOT NULL,
    triggered_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_alert_events_time
    ON alert_events (triggered_at DESC);
CREATE INDEX IF NOT EXISTS ix_alert_events_sensor_time
    ON alert_events (sensor_id, triggered_at DESC);
