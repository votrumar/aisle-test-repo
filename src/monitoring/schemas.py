from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Comparator = Literal["gt", "gte", "lt", "lte"]


class SensorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)


class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str | None
    created_at: datetime


class MeasurementCreate(BaseModel):
    sensor_id: int
    metric: str = Field(min_length=1, max_length=100)
    value: float
    unit: str = Field(min_length=1, max_length=20)
    recorded_at: datetime | None = None


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sensor_id: int
    metric: str
    value: float
    unit: str
    recorded_at: datetime


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    sensor_id: int | None = None
    metric: str = Field(min_length=1, max_length=100)
    comparator: Comparator
    threshold: float
    enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    threshold: float | None = None
    enabled: bool | None = None


class AlertRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    sensor_id: int | None
    metric: str
    comparator: Comparator
    threshold: float
    enabled: bool
    created_at: datetime


class AlertEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_id: int
    measurement_id: int
    sensor_id: int
    value: float
    triggered_at: datetime


class MeasurementResponse(BaseModel):
    measurement: MeasurementOut
    triggered_alerts: list[AlertEventOut]
