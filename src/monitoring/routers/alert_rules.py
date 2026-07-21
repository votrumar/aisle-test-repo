import hashlib

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..alerts import MAX_GLOBAL_ALERT_RULES_PER_METRIC, MAX_SENSOR_ALERT_RULES_PER_METRIC
from ..db import get_db
from ..models import AlertRule, Sensor
from ..schemas import AlertRuleCreate, AlertRuleOut, AlertRuleUpdate

router = APIRouter(prefix="/alert-rules", tags=["alert-rules"])


def _lock_enabled_rule_scope(db: Session, *, metric: str, sensor_id: int | None) -> None:
    scope = "global" if sensor_id is None else f"sensor:{sensor_id}"
    digest = hashlib.blake2b(f"alert-rule:{scope}:{metric}".encode("utf-8"), digest_size=8).digest()
    lock_id = int.from_bytes(digest, byteorder="big", signed=True)
    db.execute(select(func.pg_advisory_xact_lock(lock_id)))


def _enforce_enabled_rule_quota(
    db: Session,
    *,
    metric: str,
    sensor_id: int | None,
    exclude_rule_id: int | None = None,
) -> None:
    _lock_enabled_rule_scope(db, metric=metric, sensor_id=sensor_id)

    stmt = select(func.count()).select_from(AlertRule).where(
        AlertRule.enabled.is_(True),
        AlertRule.metric == metric,
    )
    if sensor_id is None:
        stmt = stmt.where(AlertRule.sensor_id.is_(None))
        limit = MAX_GLOBAL_ALERT_RULES_PER_METRIC
        scope = "global"
    else:
        stmt = stmt.where(AlertRule.sensor_id == sensor_id)
        limit = MAX_SENSOR_ALERT_RULES_PER_METRIC
        scope = f"sensor {sensor_id}"
    if exclude_rule_id is not None:
        stmt = stmt.where(AlertRule.id != exclude_rule_id)

    enabled_rules = db.scalar(stmt) or 0
    if enabled_rules >= limit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"enabled {scope} alert rule limit reached for metric {metric!r}",
        )


@router.post("", response_model=AlertRuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(payload: AlertRuleCreate, db: Session = Depends(get_db)) -> AlertRule:
    if payload.sensor_id is not None and db.get(Sensor, payload.sensor_id) is None:
        raise HTTPException(status_code=404, detail=f"sensor {payload.sensor_id} not found")
    if payload.enabled:
        _enforce_enabled_rule_quota(db, metric=payload.metric, sensor_id=payload.sensor_id)
    rule = AlertRule(
        name=payload.name,
        sensor_id=payload.sensor_id,
        metric=payload.metric,
        comparator=payload.comparator,
        threshold=payload.threshold,
        enabled=payload.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("", response_model=list[AlertRuleOut])
def list_rules(db: Session = Depends(get_db)) -> list[AlertRule]:
    return list(db.scalars(select(AlertRule).order_by(AlertRule.id)).all())


@router.patch("/{rule_id}", response_model=AlertRuleOut)
def update_rule(rule_id: int, payload: AlertRuleUpdate, db: Session = Depends(get_db)) -> AlertRule:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="alert rule not found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("enabled") is True:
        _enforce_enabled_rule_quota(
            db,
            metric=rule.metric,
            sensor_id=rule.sensor_id,
            exclude_rule_id=rule.id,
        )
    for key, value in data.items():
        setattr(rule, key, value)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: int, db: Session = Depends(get_db)) -> None:
    rule = db.get(AlertRule, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="alert rule not found")
    db.delete(rule)
    db.commit()
