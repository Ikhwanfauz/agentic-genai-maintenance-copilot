from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed_reference import seed_reference_data
from app.db.seed_sensor import seed_sensor_data
from app.models.enums import DataQuality, SensorType
from app.models.sensor import SensorReading


def test_seed_sensor_data_creates_expected_readings_and_trends() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    reference_time = datetime(2026, 8, 19, 0, 0, tzinfo=UTC)

    with Session(engine) as database_session:
        assets = seed_reference_data(database_session, reference_time)

        reading_count = seed_sensor_data(
            database_session,
            assets,
            reference_time,
        )
        database_session.commit()

        stored_count = database_session.scalar(select(func.count()).select_from(SensorReading))

        assert reading_count == 2520
        assert stored_count == 2520

        expected_asset_counts = {
            "P-101": 840,
            "P-102": 336,
            "P-201": 840,
            "M-101": 504,
        }

        for asset_code, expected_count in expected_asset_counts.items():
            asset_count = database_session.scalar(
                select(func.count())
                .select_from(SensorReading)
                .where(SensorReading.asset_id == assets[asset_code].id)
            )
            assert asset_count == expected_count

        p101_vibration_readings = database_session.scalars(
            select(SensorReading)
            .where(
                SensorReading.asset_id == assets["P-101"].id,
                SensorReading.sensor_type == SensorType.VIBRATION,
            )
            .order_by(SensorReading.recorded_at)
        ).all()

        assert len(p101_vibration_readings) == 168
        assert p101_vibration_readings[-1].value > p101_vibration_readings[0].value + 1.5

        bad_reading_count = database_session.scalar(
            select(func.count())
            .select_from(SensorReading)
            .where(SensorReading.quality == DataQuality.BAD)
        )
        suspect_reading_count = database_session.scalar(
            select(func.count())
            .select_from(SensorReading)
            .where(SensorReading.quality == DataQuality.SUSPECT)
        )

        assert bad_reading_count == 1
        assert suspect_reading_count == 1
