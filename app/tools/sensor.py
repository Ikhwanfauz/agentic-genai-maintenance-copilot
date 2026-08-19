from collections import defaultdict
from datetime import timedelta
from statistics import fmean

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import DataQuality, SensorType
from app.models.sensor import SensorReading
from app.schemas.sensor import (
    DataQualitySummary,
    SensorAnalysisInput,
    SensorAnalysisOutput,
    SensorMetricOutput,
    TrendDirection,
)
from app.tools.exceptions import (
    AssetNotFoundError,
    SensorDataNotFoundError,
)

TREND_THRESHOLD_PERCENT = 5.0


def calculate_linear_slope(
    readings: list[SensorReading],
) -> float:
    if len(readings) < 2:
        return 0.0

    first_timestamp = readings[0].recorded_at
    x_values = [
        (reading.recorded_at - first_timestamp).total_seconds() / 3600 for reading in readings
    ]
    y_values = [reading.value for reading in readings]

    x_mean = fmean(x_values)
    y_mean = fmean(y_values)

    denominator = sum((x_value - x_mean) ** 2 for x_value in x_values)

    if denominator == 0:
        return 0.0

    numerator = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(
            x_values,
            y_values,
            strict=True,
        )
    )

    return numerator / denominator


def classify_trend(
    percentage_change: float | None,
) -> TrendDirection:
    if percentage_change is None:
        return TrendDirection.STABLE

    if percentage_change >= TREND_THRESHOLD_PERCENT:
        return TrendDirection.INCREASING

    if percentage_change <= -TREND_THRESHOLD_PERCENT:
        return TrendDirection.DECREASING

    return TrendDirection.STABLE


def build_sensor_metric(
    sensor_type: SensorType,
    readings: list[SensorReading],
    requested_window_size: int,
) -> SensorMetricOutput:
    readings.sort(key=lambda reading: reading.recorded_at)

    effective_window_size = min(
        requested_window_size,
        max(1, len(readings) // 2),
    )

    values = [reading.value for reading in readings]
    first_window_values = values[:effective_window_size]
    latest_window_values = values[-effective_window_size:]

    first_window_mean = fmean(first_window_values)
    latest_window_mean = fmean(latest_window_values)
    absolute_change = latest_window_mean - first_window_mean

    percentage_change = (
        absolute_change / abs(first_window_mean) * 100 if abs(first_window_mean) > 1e-12 else None
    )

    return SensorMetricOutput(
        sensor_type=sensor_type,
        unit=readings[0].unit,
        reading_count=len(readings),
        first_recorded_at=readings[0].recorded_at,
        latest_recorded_at=readings[-1].recorded_at,
        minimum=round(min(values), 4),
        maximum=round(max(values), 4),
        mean=round(fmean(values), 4),
        first_window_mean=round(first_window_mean, 4),
        latest_window_mean=round(latest_window_mean, 4),
        absolute_change=round(absolute_change, 4),
        percentage_change=(round(percentage_change, 4) if percentage_change is not None else None),
        slope_per_hour=round(
            calculate_linear_slope(readings),
            6,
        ),
        trend=classify_trend(percentage_change),
    )


def analyze_sensor_data(
    database_session: Session,
    tool_input: SensorAnalysisInput,
) -> SensorAnalysisOutput:
    asset_id = database_session.scalar(
        select(Asset.id).where(Asset.asset_code == tool_input.asset_code)
    )

    if asset_id is None:
        raise AssetNotFoundError(tool_input.asset_code)

    sensor_filters = [
        SensorReading.asset_id == asset_id,
    ]

    if tool_input.sensor_types is not None:
        sensor_filters.append(SensorReading.sensor_type.in_(tool_input.sensor_types))

    analysis_end = database_session.scalar(
        select(func.max(SensorReading.recorded_at)).where(*sensor_filters)
    )

    if analysis_end is None:
        raise SensorDataNotFoundError(tool_input.asset_code)

    analysis_start = analysis_end - timedelta(hours=tool_input.lookback_hours)

    readings = database_session.scalars(
        select(SensorReading)
        .where(
            *sensor_filters,
            SensorReading.recorded_at > analysis_start,
            SensorReading.recorded_at <= analysis_end,
        )
        .order_by(
            SensorReading.sensor_type,
            SensorReading.recorded_at,
        )
    ).all()

    if not readings:
        raise SensorDataNotFoundError(tool_input.asset_code)

    good_readings = sum(reading.quality == DataQuality.GOOD for reading in readings)
    suspect_readings = sum(reading.quality == DataQuality.SUSPECT for reading in readings)
    bad_readings = sum(reading.quality == DataQuality.BAD for reading in readings)

    analyzed_readings = [
        reading
        for reading in readings
        if reading.quality == DataQuality.GOOD
        or (tool_input.include_suspect and reading.quality == DataQuality.SUSPECT)
    ]

    if not analyzed_readings:
        raise SensorDataNotFoundError(tool_input.asset_code)

    grouped_readings: dict[
        SensorType,
        list[SensorReading],
    ] = defaultdict(list)

    for reading in analyzed_readings:
        grouped_readings[reading.sensor_type].append(reading)

    metrics = [
        build_sensor_metric(
            sensor_type,
            sensor_readings,
            tool_input.window_size,
        )
        for sensor_type, sensor_readings in sorted(
            grouped_readings.items(),
            key=lambda item: item[0].value,
        )
    ]

    return SensorAnalysisOutput(
        asset_code=tool_input.asset_code,
        analysis_start=analysis_start,
        analysis_end=analysis_end,
        lookback_hours=tool_input.lookback_hours,
        trend_threshold_percent=TREND_THRESHOLD_PERCENT,
        quality=DataQualitySummary(
            total_readings=len(readings),
            analyzed_readings=len(analyzed_readings),
            excluded_readings=(len(readings) - len(analyzed_readings)),
            good_readings=good_readings,
            suspect_readings=suspect_readings,
            bad_readings=bad_readings,
        ),
        metrics=metrics,
    )
