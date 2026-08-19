from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed import EXPECTED_COUNTS, SeedSummary, seed_database


def test_seed_database_is_complete_and_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    reference_time = datetime(2026, 8, 19, tzinfo=UTC)

    with Session(engine, expire_on_commit=False) as database_session:
        first_result = seed_database(
            database_session,
            reference_time,
        )
        second_result = seed_database(
            database_session,
            reference_time,
        )

    assert first_result.seeded is True
    assert second_result.seeded is False

    assert first_result.assets == EXPECTED_COUNTS["assets"]
    assert first_result.maintenance_records == EXPECTED_COUNTS["maintenance_records"]
    assert first_result.sensor_readings == EXPECTED_COUNTS["sensor_readings"]
    assert first_result.work_orders == EXPECTED_COUNTS["work_orders"]
    assert first_result.approvals == EXPECTED_COUNTS["approvals"]

    assert second_result == SeedSummary(
        seeded=False,
        assets=EXPECTED_COUNTS["assets"],
        maintenance_records=EXPECTED_COUNTS["maintenance_records"],
        sensor_readings=EXPECTED_COUNTS["sensor_readings"],
        work_orders=EXPECTED_COUNTS["work_orders"],
        approvals=EXPECTED_COUNTS["approvals"],
    )
