from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed_reference import seed_reference_data
from app.models.enums import MaintenanceType
from app.schemas.maintenance import MaintenanceHistoryInput
from app.tools.exceptions import AssetNotFoundError
from app.tools.maintenance import query_maintenance_history

REFERENCE_TIME = datetime(2026, 8, 19, tzinfo=UTC)


@pytest.fixture
def seeded_database_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as database_session:
        seed_reference_data(
            database_session,
            REFERENCE_TIME,
        )
        database_session.commit()

        yield database_session


def test_query_maintenance_history_returns_latest_records_first(
    seeded_database_session: Session,
) -> None:
    result = query_maintenance_history(
        seeded_database_session,
        MaintenanceHistoryInput(asset_code="P-101"),
    )

    assert result.asset_code == "P-101"
    assert result.total_matching_records == 3
    assert result.returned_record_count == 3
    assert result.has_more is False
    assert result.records[0].summary == "Routine vibration inspection"
    assert result.records[-1].summary == ("Pump and motor alignment correction")


def test_query_maintenance_history_filters_by_type(
    seeded_database_session: Session,
) -> None:
    result = query_maintenance_history(
        seeded_database_session,
        MaintenanceHistoryInput(
            asset_code="M-101",
            maintenance_type=MaintenanceType.PREDICTIVE,
        ),
    )

    assert result.total_matching_records == 1
    assert result.records[0].maintenance_type == (MaintenanceType.PREDICTIVE)
    assert result.records[0].summary == ("Motor current and vibration review")


def test_query_maintenance_history_filters_by_time_range(
    seeded_database_session: Session,
) -> None:
    result = query_maintenance_history(
        seeded_database_session,
        MaintenanceHistoryInput(
            asset_code="P-101",
            start_time=REFERENCE_TIME - timedelta(days=30),
            end_time=REFERENCE_TIME,
        ),
    )

    assert result.total_matching_records == 1
    assert result.records[0].summary == "Routine vibration inspection"


def test_query_maintenance_history_reports_limited_results(
    seeded_database_session: Session,
) -> None:
    result = query_maintenance_history(
        seeded_database_session,
        MaintenanceHistoryInput(
            asset_code="P-101",
            limit=2,
        ),
    )

    assert result.total_matching_records == 3
    assert result.returned_record_count == 2
    assert result.has_more is True


def test_query_maintenance_history_returns_empty_for_no_matches(
    seeded_database_session: Session,
) -> None:
    result = query_maintenance_history(
        seeded_database_session,
        MaintenanceHistoryInput(
            asset_code="P-102",
            maintenance_type=MaintenanceType.CORRECTIVE,
        ),
    )

    assert result.total_matching_records == 0
    assert result.returned_record_count == 0
    assert result.has_more is False
    assert result.records == []


def test_query_maintenance_history_raises_for_unknown_asset(
    seeded_database_session: Session,
) -> None:
    with pytest.raises(
        AssetNotFoundError,
        match="Asset 'P-999' was not found.",
    ):
        query_maintenance_history(
            seeded_database_session,
            MaintenanceHistoryInput(asset_code="P-999"),
        )


def test_maintenance_history_input_rejects_invalid_range() -> None:
    with pytest.raises(
        ValidationError,
        match="start_time must be earlier",
    ):
        MaintenanceHistoryInput(
            asset_code="P-101",
            start_time=REFERENCE_TIME,
            end_time=REFERENCE_TIME - timedelta(days=1),
        )


def test_maintenance_history_input_rejects_excessive_limit() -> None:
    with pytest.raises(ValidationError):
        MaintenanceHistoryInput(
            asset_code="P-101",
            limit=100,
        )
