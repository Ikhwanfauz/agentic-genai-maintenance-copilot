from datetime import UTC, datetime

import chromadb
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

REFERENCE_TIME = datetime(
    2026,
    8,
    19,
    tzinfo=UTC,
)
COLLECTION_NAME = "evaluation_mutation_docs"


def create_database_session() -> Session:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    database_session = Session(
        engine,
        expire_on_commit=False,
    )

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

    return database_session


def create_vector_client():
    vector_client = chromadb.EphemeralClient()
    collection = vector_client.get_or_create_collection(
        name=COLLECTION_NAME,
    )
    collection.upsert(
        ids=["doc-one", "doc-two"],
        documents=[
            "Pump vibration guidance.",
            "Maintenance approval guidance.",
        ],
        embeddings=[
            [1.0, 0.0],
            [0.0, 1.0],
        ],
    )

    return vector_client


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


def test_empty_sensor_mutation_is_asset_scoped() -> None:
    database_session = create_database_session()
    vector_client = create_vector_client()
    comparison_count = count_sensor_readings(
        database_session,
        "P-201",
    )

    try:
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
    finally:
        database_session.close()


def test_empty_maintenance_mutation_is_asset_scoped() -> None:
    database_session = create_database_session()
    vector_client = create_vector_client()
    comparison_count = count_maintenance_records(
        database_session,
        "P-201",
    )

    try:
        apply_fixture_mutations(
            [
                EvaluationFixtureMutation(
                    mutation_type=(FixtureMutationType.EMPTY_MAINTENANCE_HISTORY),
                    asset_code="P-101",
                )
            ],
            database_session=database_session,
            vector_client=vector_client,
            engineering_docs_collection=COLLECTION_NAME,
        )

        assert count_maintenance_records(database_session, "P-101") == 0
        assert count_maintenance_records(database_session, "P-201") == comparison_count
    finally:
        database_session.close()


def test_limited_history_retains_only_declared_records() -> None:
    database_session = create_database_session()
    vector_client = create_vector_client()
    record_ids = list(
        database_session.scalars(
            select(MaintenanceRecord.id)
            .join(Asset)
            .where(Asset.asset_code == "P-101")
            .order_by(MaintenanceRecord.id)
        )
    )
    retained_record_id = record_ids[0]

    try:
        apply_fixture_mutations(
            [
                EvaluationFixtureMutation(
                    mutation_type=(FixtureMutationType.LIMITED_MAINTENANCE_HISTORY),
                    asset_code="P-101",
                    retained_maintenance_record_ids=[
                        retained_record_id,
                    ],
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
    finally:
        database_session.close()


def test_empty_document_mutation_clears_only_collection() -> None:
    database_session = create_database_session()
    vector_client = create_vector_client()
    baseline_maintenance_count = count_maintenance_records(
        database_session,
        "P-101",
    )

    try:
        apply_fixture_mutations(
            [
                EvaluationFixtureMutation(
                    mutation_type=(FixtureMutationType.EMPTY_ENGINEERING_DOCUMENTS),
                )
            ],
            database_session=database_session,
            vector_client=vector_client,
            engineering_docs_collection=COLLECTION_NAME,
        )

        assert vector_client.get_collection(name=COLLECTION_NAME).count() == 0
        assert count_maintenance_records(database_session, "P-101") == baseline_maintenance_count
    finally:
        database_session.close()


def test_unknown_asset_mutation_fails_without_database_change() -> None:
    database_session = create_database_session()
    vector_client = create_vector_client()
    baseline_count = count_sensor_readings(
        database_session,
        "P-101",
    )

    try:
        with pytest.raises(
            ValueError,
            match="was not found",
        ):
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
    finally:
        database_session.close()
