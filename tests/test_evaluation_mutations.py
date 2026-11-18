from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed_reference import seed_reference_data
from app.db.seed_sensor import seed_sensor_data
from app.evaluation.fixtures import (
    EvaluationFixtureMutation,
    FixtureMutationType,
)
from app.evaluation.mutations import apply_fixture_mutations
from app.models.asset import Asset
from app.models.maintenance import MaintenanceRecord
from app.models.sensor import SensorReading
from app.rag.vector_store import SQLVectorStore, VectorDocument

REFERENCE_TIME = datetime(2026, 8, 19, tzinfo=UTC)
COLLECTION_NAME = "evaluation_mutation_docs"


@pytest.fixture
def mutation_environment():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as database_session:
        assets = seed_reference_data(database_session, REFERENCE_TIME)
        seed_sensor_data(database_session, assets, REFERENCE_TIME)
        database_session.commit()

    vector_client = SQLVectorStore(engine)
    documents = [
        VectorDocument(
            chunk_id="doc-one",
            content="Pump vibration guidance.",
            metadata={},
            embedding=[1.0, 0.0],
        ),
        VectorDocument(
            chunk_id="doc-two",
            content="Maintenance approval guidance.",
            metadata={},
            embedding=[0.0, 1.0],
        ),
    ]
    vector_client.replace_collection(
        COLLECTION_NAME,
        documents,
        embedding_model="evaluation-mutation-test",
    )
    vector_client.replace_collection(
        "unrelated_docs",
        documents[:1],
        embedding_model="evaluation-mutation-test",
    )

    try:
        with Session(engine, expire_on_commit=False) as database_session:
            yield database_session, vector_client
    finally:
        engine.dispose()


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


def count_maintenance_records(
    database_session: Session,
    asset_code: str,
) -> int:
    return int(
        database_session.scalar(
            select(func.count())
            .select_from(MaintenanceRecord)
            .join(Asset)
            .where(Asset.asset_code == asset_code)
        )
        or 0
    )


def test_empty_sensor_mutation_is_asset_scoped(mutation_environment) -> None:
    database_session, vector_client = mutation_environment
    comparison_count = count_sensor_readings(database_session, "P-201")

    apply_fixture_mutations(
        [
            EvaluationFixtureMutation(
                mutation_type=FixtureMutationType.EMPTY_SENSOR_DATA,
                asset_code="P-101",
            )
        ],
        database_session=database_session,
        vector_client=vector_client,
        engineering_docs_collection=COLLECTION_NAME,
    )

    assert count_sensor_readings(database_session, "P-101") == 0
    assert count_sensor_readings(database_session, "P-201") == comparison_count


def test_empty_maintenance_mutation_is_asset_scoped(mutation_environment) -> None:
    database_session, vector_client = mutation_environment
    comparison_count = count_maintenance_records(database_session, "P-201")

    apply_fixture_mutations(
        [
            EvaluationFixtureMutation(
                mutation_type=FixtureMutationType.EMPTY_MAINTENANCE_HISTORY,
                asset_code="P-101",
            )
        ],
        database_session=database_session,
        vector_client=vector_client,
        engineering_docs_collection=COLLECTION_NAME,
    )

    assert count_maintenance_records(database_session, "P-101") == 0
    assert count_maintenance_records(database_session, "P-201") == comparison_count


def test_limited_history_retains_only_declared_records(mutation_environment) -> None:
    database_session, vector_client = mutation_environment
    record_ids = list(
        database_session.scalars(
            select(MaintenanceRecord.id)
            .join(Asset)
            .where(Asset.asset_code == "P-101")
            .order_by(MaintenanceRecord.id)
        )
    )
    retained_record_id = record_ids[0]

    apply_fixture_mutations(
        [
            EvaluationFixtureMutation(
                mutation_type=FixtureMutationType.LIMITED_MAINTENANCE_HISTORY,
                asset_code="P-101",
                retained_maintenance_record_ids=[retained_record_id],
            )
        ],
        database_session=database_session,
        vector_client=vector_client,
        engineering_docs_collection=COLLECTION_NAME,
    )

    remaining_ids = list(
        database_session.scalars(
            select(MaintenanceRecord.id)
            .join(Asset)
            .where(Asset.asset_code == "P-101")
            .order_by(MaintenanceRecord.id)
        )
    )

    assert remaining_ids == [retained_record_id]


def test_empty_document_mutation_clears_only_collection(mutation_environment) -> None:
    database_session, vector_client = mutation_environment
    baseline_count = count_maintenance_records(database_session, "P-101")

    apply_fixture_mutations(
        [
            EvaluationFixtureMutation(
                mutation_type=FixtureMutationType.EMPTY_ENGINEERING_DOCUMENTS,
            )
        ],
        database_session=database_session,
        vector_client=vector_client,
        engineering_docs_collection=COLLECTION_NAME,
    )

    assert vector_client.count(COLLECTION_NAME) == 0
    assert vector_client.count("unrelated_docs") == 1
    assert count_maintenance_records(database_session, "P-101") == baseline_count


def test_unknown_asset_mutation_fails_without_database_change(mutation_environment) -> None:
    database_session, vector_client = mutation_environment
    baseline_count = count_sensor_readings(database_session, "P-101")

    with pytest.raises(ValueError, match="was not found"):
        apply_fixture_mutations(
            [
                EvaluationFixtureMutation(
                    mutation_type=FixtureMutationType.EMPTY_SENSOR_DATA,
                    asset_code="Z-999",
                )
            ],
            database_session=database_session,
            vector_client=vector_client,
            engineering_docs_collection=COLLECTION_NAME,
        )

    assert count_sensor_readings(database_session, "P-101") == baseline_count
