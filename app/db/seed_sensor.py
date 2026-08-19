import random
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.enums import DataQuality, SensorType
from app.models.sensor import SensorReading


@dataclass(frozen=True)
class SensorProfile:
    baseline: float
    trend: float
    noise: float
    unit: str


SENSOR_PROFILES: dict[str, dict[SensorType, SensorProfile]] = {
    "P-101": {
        SensorType.VIBRATION: SensorProfile(3.2, 2.4, 0.12, "mm/s RMS"),
        SensorType.TEMPERATURE: SensorProfile(67.0, 10.0, 0.4, "degC"),
        SensorType.SUCTION_PRESSURE: SensorProfile(2.1, -0.1, 0.03, "bar"),
        SensorType.DISCHARGE_PRESSURE: SensorProfile(6.8, -0.5, 0.05, "bar"),
        SensorType.FLOW_RATE: SensorProfile(220.0, -15.0, 1.5, "m3/h"),
    },
    "P-102": {
        SensorType.VIBRATION: SensorProfile(0.2, 0.0, 0.03, "mm/s RMS"),
        SensorType.TEMPERATURE: SensorProfile(29.0, 0.5, 0.2, "degC"),
    },
    "P-201": {
        SensorType.VIBRATION: SensorProfile(2.4, 0.2, 0.08, "mm/s RMS"),
        SensorType.TEMPERATURE: SensorProfile(61.0, 1.0, 0.3, "degC"),
        SensorType.SUCTION_PRESSURE: SensorProfile(2.5, 0.0, 0.03, "bar"),
        SensorType.DISCHARGE_PRESSURE: SensorProfile(7.2, -0.1, 0.04, "bar"),
        SensorType.FLOW_RATE: SensorProfile(180.0, -2.0, 1.0, "m3/h"),
    },
    "M-101": {
        SensorType.VIBRATION: SensorProfile(2.5, 1.7, 0.1, "mm/s RMS"),
        SensorType.TEMPERATURE: SensorProfile(63.0, 7.0, 0.35, "degC"),
        SensorType.MOTOR_CURRENT: SensorProfile(41.0, 5.0, 0.25, "A"),
    },
}


def determine_data_quality(
    asset_code: str,
    sensor_type: SensorType,
    point_index: int,
) -> DataQuality:
    if asset_code == "P-102" and sensor_type == SensorType.TEMPERATURE and point_index == 50:
        return DataQuality.BAD

    if asset_code == "P-201" and sensor_type == SensorType.FLOW_RATE and point_index == 100:
        return DataQuality.SUSPECT

    return DataQuality.GOOD


def seed_sensor_data(
    database_session: Session,
    assets: dict[str, Asset],
    reference_time: datetime,
    days: int = 7,
    interval_hours: int = 1,
    random_seed: int = 42,
) -> int:
    random_generator = random.Random(random_seed)
    number_of_points = days * 24 // interval_hours
    start_time = reference_time - timedelta(days=days)

    sensor_readings: list[SensorReading] = []

    for asset_code, sensor_profiles in SENSOR_PROFILES.items():
        asset = assets[asset_code]

        for point_index in range(number_of_points):
            recorded_at = start_time + timedelta(hours=point_index * interval_hours)
            progress = point_index / max(number_of_points - 1, 1)

            for sensor_type, profile in sensor_profiles.items():
                value = (
                    profile.baseline
                    + profile.trend * progress
                    + random_generator.uniform(-profile.noise, profile.noise)
                )

                sensor_readings.append(
                    SensorReading(
                        asset=asset,
                        recorded_at=recorded_at,
                        sensor_type=sensor_type,
                        value=round(value, 3),
                        unit=profile.unit,
                        quality=determine_data_quality(
                            asset_code,
                            sensor_type,
                            point_index,
                        ),
                        source="synthetic-seed",
                    )
                )

    database_session.add_all(sensor_readings)
    return len(sensor_readings)
