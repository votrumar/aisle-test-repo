from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Sensor(Base):
    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    location: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSONB, server_default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    measurements: Mapped[list["Measurement"]] = relationship(back_populates="sensor")


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    sensor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False
    )
    metric: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sensor: Mapped[Sensor] = relationship(back_populates="measurements")


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (
        CheckConstraint("comparator IN ('gt','gte','lt','lte')", name="alert_rules_comparator_chk"),
        Index("ix_alert_rules_enabled_metric_sensor", "enabled", "metric", "sensor_id", "id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    sensor_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sensors.id", ondelete="CASCADE"), nullable=True
    )
    metric: Mapped[str] = mapped_column(String, nullable=False)
    comparator: Mapped[str] = mapped_column(String, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("alert_rules.id", ondelete="CASCADE"), nullable=False
    )
    measurement_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("measurements.id", ondelete="CASCADE"), nullable=False
    )
    sensor_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
