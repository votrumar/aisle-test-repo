from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import AlertEvent, AlertRule, Measurement

_COMPARATORS = {
    "gt": lambda v, t: v > t,
    "gte": lambda v, t: v >= t,
    "lt": lambda v, t: v < t,
    "lte": lambda v, t: v <= t,
}


def evaluate_measurement(db: Session, measurement: Measurement) -> list[AlertEvent]:
    rules = db.scalars(
        select(AlertRule).where(
            AlertRule.enabled.is_(True),
            AlertRule.metric == measurement.metric,
            or_(AlertRule.sensor_id.is_(None), AlertRule.sensor_id == measurement.sensor_id),
        )
    ).all()

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
