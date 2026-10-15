from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import AlertEvent, AlertRule, Measurement

MAX_GLOBAL_ALERT_RULES_PER_METRIC = 32
MAX_SENSOR_ALERT_RULES_PER_METRIC = 32
MAX_RULES_PER_MEASUREMENT = MAX_GLOBAL_ALERT_RULES_PER_METRIC + MAX_SENSOR_ALERT_RULES_PER_METRIC

_COMPARATORS = {
    "gt": lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
}


def evaluate_measurement(db: Session, measurement: Measurement) -> list[AlertEvent]:
    rules = db.scalars(
        select(AlertRule)
        .where(
            AlertRule.enabled.is_(True),
            AlertRule.metric == measurement.metric,
            or_(AlertRule.sensor_id.is_(None), AlertRule.sensor_id == measurement.sensor_id),
        )
        .order_by(AlertRule.id)
        .limit(MAX_RULES_PER_MEASUREMENT + 1)
    ).all()
    if len(rules) > MAX_RULES_PER_MEASUREMENT:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="too many enabled alert rules for this measurement",
        )

    events: list[AlertEvent] = []
    for rule in rules:
        if _COMPARATORS[rule.comparator](measurement.value, rule.threshold):
            events.append(
                AlertEvent(
                    rule_id=rule.id,
                    measurement_id=measurement.id,
                    sensor_id=measurement.sensor_id,
                    value=measurement.value,
                )
            )
    if events:
        db.add_all(events)
        db.flush()
    return events
