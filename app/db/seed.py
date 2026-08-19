from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.seed_reference import seed_reference_data
from app.db.seed_sensor import seed_sensor_data
from app.db.session import SessionLocal
from app.models.approval import Approval
from app.models.asset import Asset
from app.models.maintenance import MaintenanceRecord
from app.models.sensor import SensorReading
from app.models.work_order import WorkOrder


@dataclass(frozen=True)
class SeedSummary:
    seeded: bool
    assets: int
    maintenance_records: int
    sensor_readings: int
    work_orders: int
    approvals: int


EXPECTED_COUNTS = {
    "assets": 4,
    "maintenance_records": 7,
    "sensor_readings": 2520,
    "work_orders": 2,
    "approvals": 2,
}


def count_rows(database_session: Session, model: type) -> int:
    count = database_session.scalar(select(func.count()).select_from(model))
    return int(count or 0)


def build_seed_summary(
    database_session: Session,
    *,
    seeded: bool,
) -> SeedSummary:
    return SeedSummary(
        seeded=seeded,
        assets=count_rows(database_session, Asset),
        maintenance_records=count_rows(
            database_session,
            MaintenanceRecord,
        ),
        sensor_readings=count_rows(database_session, SensorReading),
        work_orders=count_rows(database_session, WorkOrder),
        approvals=count_rows(database_session, Approval),
    )


def validate_existing_seed(summary: SeedSummary) -> None:
    actual_counts = {
        "assets": summary.assets,
        "maintenance_records": summary.maintenance_records,
        "sensor_readings": summary.sensor_readings,
        "work_orders": summary.work_orders,
        "approvals": summary.approvals,
    }

    if actual_counts != EXPECTED_COUNTS:
        raise RuntimeError(
            "Database contains partial or unexpected seed data. "
            f"Expected {EXPECTED_COUNTS}, received {actual_counts}."
        )


def seed_database(
    database_session: Session,
    reference_time: datetime,
) -> SeedSummary:
    existing_asset_count = count_rows(database_session, Asset)

    if existing_asset_count:
        summary = build_seed_summary(
            database_session,
            seeded=False,
        )
        validate_existing_seed(summary)
        return summary

    try:
        assets = seed_reference_data(
            database_session,
            reference_time,
        )
        seed_sensor_data(
            database_session,
            assets,
            reference_time,
        )
        database_session.commit()
    except Exception:
        database_session.rollback()
        raise

    summary = build_seed_summary(
        database_session,
        seeded=True,
    )
    validate_existing_seed(summary)
    return summary


def main() -> None:
    reference_time = datetime.now(UTC).replace(
        minute=0,
        second=0,
        microsecond=0,
    )

    with SessionLocal() as database_session:
        summary = seed_database(
            database_session,
            reference_time,
        )

    action = "created" if summary.seeded else "already present"

    print(f"Seed data: {action}")
    print(f"Assets: {summary.assets}")
    print(f"Maintenance records: {summary.maintenance_records}")
    print(f"Sensor readings: {summary.sensor_readings}")
    print(f"Work orders: {summary.work_orders}")
    print(f"Approvals: {summary.approvals}")


if __name__ == "__main__":
    main()
