from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed_reference import seed_reference_data
from app.db.seed_sensor import seed_sensor_data
from app.models.enums import SensorType
from app.schemas.sensor import (
    SensorAnalysisInput,
    TrendDirection,
)
from app.tools.exceptions import (
    AssetNotFoundError,
    SensorDataNotFoundError,
)
from app.tools.sensor import analyze_sensor_data

REFERENCE_TIME = datetime(2026, 8, 19, tzinfo=UTC)


@pytest.fixture
def seeded_database_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as database_session:
        assets = seed_reference_data(
            database_session,
            REFERENCE_TIME,
        )
        seed_sensor_data(
            database_session,
            assets,
            REFERENCE_TIME,
        )
        database_session.commit()

        yield database_session


def metric_by_type(result, sensor_type: SensorType):
    return next(metric for metric in result.metrics if metric.sensor_type == sensor_type)


def test_analyze_sensor_data_detects_p101_degradation(
    seeded_database_session: Session,
) -> None:
    result = analyze_sensor_data(
        seeded_database_session,
        SensorAnalysisInput(asset_code="P-101"),
    )

    vibration = metric_by_type(
        result,
        SensorType.VIBRATION,
    )
    flow_rate = metric_by_type(
        result,
        SensorType.FLOW_RATE,
    )

    assert len(result.metrics) == 5
    assert result.quality.total_readings == 840
    assert result.quality.analyzed_readings == 840
    assert vibration.trend == TrendDirection.INCREASING
    assert vibration.percentage_change is not None
    assert vibration.percentage_change > 50
    assert vibration.slope_per_hour > 0
    assert flow_rate.trend == TrendDirection.DECREASING


def test_analyze_sensor_data_excludes_bad_readings(
    seeded_database_session: Session,
) -> None:
    result = analyze_sensor_data(
        seeded_database_session,
        SensorAnalysisInput(asset_code="P-102"),
    )

    temperature = metric_by_type(
        result,
        SensorType.TEMPERATURE,
    )

    assert result.quality.total_readings == 336
    assert result.quality.good_readings == 335
    assert result.quality.bad_readings == 1
    assert result.quality.excluded_readings == 1
    assert temperature.reading_count == 167


def test_analyze_sensor_data_can_include_suspect_readings(
    seeded_database_session: Session,
) -> None:
    excluded_result = analyze_sensor_data(
        seeded_database_session,
        SensorAnalysisInput(asset_code="P-201"),
    )
    included_result = analyze_sensor_data(
        seeded_database_session,
        SensorAnalysisInput(
            asset_code="P-201",
            include_suspect=True,
        ),
    )

    assert excluded_result.quality.suspect_readings == 1
    assert excluded_result.quality.analyzed_readings == 839
    assert included_result.quality.analyzed_readings == 840
    assert included_result.quality.excluded_readings == 0


def test_analyze_sensor_data_filters_type_and_time_window(
    seeded_database_session: Session,
) -> None:
    result = analyze_sensor_data(
        seeded_database_session,
        SensorAnalysisInput(
            asset_code="M-101",
            sensor_types=[SensorType.MOTOR_CURRENT],
            lookback_hours=24,
            window_size=6,
        ),
    )

    assert len(result.metrics) == 1
    assert result.metrics[0].sensor_type == (SensorType.MOTOR_CURRENT)
    assert result.metrics[0].reading_count == 24


def test_analyze_sensor_data_raises_for_unknown_asset(
    seeded_database_session: Session,
) -> None:
    with pytest.raises(
        AssetNotFoundError,
        match="Asset 'P-999' was not found.",
    ):
        analyze_sensor_data(
            seeded_database_session,
            SensorAnalysisInput(asset_code="P-999"),
        )


def test_analyze_sensor_data_raises_when_sensor_type_is_missing(
    seeded_database_session: Session,
) -> None:
    with pytest.raises(
        SensorDataNotFoundError,
        match="No sensor readings were found",
    ):
        analyze_sensor_data(
            seeded_database_session,
            SensorAnalysisInput(
                asset_code="P-102",
                sensor_types=[SensorType.MOTOR_CURRENT],
            ),
        )


def test_sensor_analysis_input_rejects_invalid_arguments() -> None:
    with pytest.raises(ValidationError):
        SensorAnalysisInput(
            asset_code="P-101",
            sensor_types=[],
            lookback_hours=1,
        )
