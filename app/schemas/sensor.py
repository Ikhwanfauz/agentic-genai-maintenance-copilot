from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import SensorType
from app.schemas.common import AssetCodeInput


class TrendDirection(StrEnum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    STABLE = "stable"


class SensorAnalysisInput(AssetCodeInput):
    sensor_types: list[SensorType] | None = None
    lookback_hours: int = Field(default=168, ge=2, le=720)
    window_size: int = Field(default=24, ge=1, le=168)
    include_suspect: bool = False

    @field_validator("sensor_types")
    @classmethod
    def validate_sensor_types(
        cls,
        value: list[SensorType] | None,
    ) -> list[SensorType] | None:
        if value == []:
            raise ValueError("sensor_types must not be an empty list.")

        if value is None:
            return None

        return list(dict.fromkeys(value))


class DataQualitySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_readings: int
    analyzed_readings: int
    excluded_readings: int
    good_readings: int
    suspect_readings: int
    bad_readings: int


class SensorMetricOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensor_type: SensorType
    unit: str
    reading_count: int
    first_recorded_at: datetime
    latest_recorded_at: datetime
    minimum: float
    maximum: float
    mean: float
    first_window_mean: float
    latest_window_mean: float
    absolute_change: float
    percentage_change: float | None
    slope_per_hour: float
    trend: TrendDirection


class SensorAnalysisOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_code: str
    analysis_start: datetime
    analysis_end: datetime
    lookback_hours: int
    trend_threshold_percent: float
    quality: DataQualitySummary
    metrics: list[SensorMetricOutput] = Field(default_factory=list)
