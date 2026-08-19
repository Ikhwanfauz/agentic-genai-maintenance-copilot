from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed_reference import seed_reference_data
from app.schemas.asset import AssetDetailsInput
from app.tools.asset import get_asset_details
from app.tools.exceptions import AssetNotFoundError


@pytest.fixture
def seeded_database_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as database_session:
        seed_reference_data(
            database_session,
            datetime(2026, 8, 19, tzinfo=UTC),
        )
        database_session.commit()

        yield database_session


def test_get_asset_details_returns_structured_pump_data(
    seeded_database_session: Session,
) -> None:
    tool_input = AssetDetailsInput(asset_code="P-101")

    result = get_asset_details(
        seeded_database_session,
        tool_input,
    )

    assert result.asset_code == "P-101"
    assert result.name == "Main Cooling Water Pump"
    assert result.asset_type.value == "pump"
    assert result.status.value == "operational"
    assert result.criticality.value == "critical"
    assert result.parent_asset_code is None
    assert result.child_asset_codes == ["M-101"]


def test_get_asset_details_returns_parent_asset(
    seeded_database_session: Session,
) -> None:
    result = get_asset_details(
        seeded_database_session,
        AssetDetailsInput(asset_code="M-101"),
    )

    assert result.asset_code == "M-101"
    assert result.parent_asset_code == "P-101"
    assert result.child_asset_codes == []


def test_asset_details_input_normalizes_asset_code() -> None:
    tool_input = AssetDetailsInput(asset_code="  p-101  ")

    assert tool_input.asset_code == "P-101"


def test_get_asset_details_raises_when_asset_is_missing(
    seeded_database_session: Session,
) -> None:
    with pytest.raises(
        AssetNotFoundError,
        match="Asset 'P-999' was not found.",
    ):
        get_asset_details(
            seeded_database_session,
            AssetDetailsInput(asset_code="P-999"),
        )


def test_asset_details_input_rejects_invalid_arguments() -> None:
    with pytest.raises(ValidationError):
        AssetDetailsInput(
            asset_code="invalid",
            unexpected_argument="not allowed",
        )
