from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.evaluation.environment import (
    open_evaluation_scenario_environment,
)
from app.evaluation.fixture_registry import get_fixture_plan
from app.models.asset import Asset
from app.models.sensor import SensorReading


def count_sensor_readings(
    database_session: Session,
    asset_code: str,
) -> int:
    return int(
        database_session.scalar(
            select(func.count())
            .select_from(SensorReading)
            .join(Asset)
            .where(Asset.asset_code == asset_code)
        )
        or 0
    )


def test_environment_seeds_real_sql_chroma_and_tools(
    tmp_path: Path,
) -> None:
    fixture = get_fixture_plan("p101-grounded-monitoring")

    with open_evaluation_scenario_environment(
        tmp_path / "normal",
        fixture,
    ) as environment:
        with environment.session_factory() as database_session:
            asset_count = int(database_session.scalar(select(func.count()).select_from(Asset)) or 0)
            sensor_count = int(
                database_session.scalar(select(func.count()).select_from(SensorReading)) or 0
            )

        assert asset_count == 4
        assert sensor_count == 2520
        assert (
            environment.vector_client.get_collection(
                name=environment.engineering_docs_collection
            ).count()
            == 9
        )
        assert {tool.name for tool in environment.tools} == {
            "get_asset_details",
            "query_maintenance_history",
            "analyze_sensor_data",
            "search_engineering_docs",
        }
        assert not environment.checkpoint_path.exists()


def test_environment_applies_asset_scoped_sensor_mutation(
    tmp_path: Path,
) -> None:
    fixture = get_fixture_plan("p101-sensor-data-unavailable")

    with open_evaluation_scenario_environment(
        tmp_path / "empty-sensor",
        fixture,
    ) as environment:
        with environment.session_factory() as database_session:
            p101_count = count_sensor_readings(
                database_session,
                "P-101",
            )
            p201_count = count_sensor_readings(
                database_session,
                "P-201",
            )

        assert p101_count == 0
        assert p201_count > 0


def test_environment_applies_empty_document_mutation(
    tmp_path: Path,
) -> None:
    fixture = get_fixture_plan("p101-empty-rag-results")

    with open_evaluation_scenario_environment(
        tmp_path / "empty-documents",
        fixture,
    ) as environment:
        collection = environment.vector_client.get_collection(
            name=environment.engineering_docs_collection
        )

        assert collection.count() == 0


def test_environment_rejects_existing_database(
    tmp_path: Path,
) -> None:
    fixture = get_fixture_plan("p101-grounded-monitoring")
    working_directory = tmp_path / "existing"

    with open_evaluation_scenario_environment(
        working_directory,
        fixture,
    ):
        pass

    try:
        with open_evaluation_scenario_environment(
            working_directory,
            fixture,
        ):
            pass
    except FileExistsError as error:
        assert "Evaluation database already exists" in str(error)
    else:
        raise AssertionError("An existing evaluation database must be rejected.")
