import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Comparator = Literal["gt", "gte", "lt", "lte"]

_METADATA_KEY_RE = re.compile(r"^[a-z][a-z0-9_-]{0,30}$")

# Denylist for attribute-like keys that become dangerous if ever rendered into HTML.
# (The dashboard previously rendered metadata keys through Jinja2's `xmlattr` filter.)
_DISALLOWED_METADATA_KEYS = {"style"}
_DISALLOWED_METADATA_PREFIXES = ("on",)  # e.g. onmouseover


def _sanitize_metadata(metadata: dict[str, str], *, strict: bool) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    for key, value in metadata.items():
        if not _METADATA_KEY_RE.fullmatch(key):
            if strict:
                raise ValueError(f"metadata key {key!r} is not allowed")
            continue

        if key in _DISALLOWED_METADATA_KEYS or key.startswith(_DISALLOWED_METADATA_PREFIXES):
            if strict:
                raise ValueError(f"metadata key {key!r} is not allowed")
            continue

        sanitized[key] = value

    return sanitized


class SensorCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_metadata_keys(self) -> "SensorCreate":
        # Strict validation for write paths.
        self.metadata = _sanitize_metadata(self.metadata, strict=True)
        return self


class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: str | None
    created_at: datetime
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_metadata_keys(self) -> "SensorOut":
        # Be tolerant when reading older rows; drop keys that are not allowed.
        self.metadata = _sanitize_metadata(self.metadata, strict=False)
        return self


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
