from collections.abc import Sequence

from chromadb.api import ClientAPI
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.evaluation.fixtures import (
    EvaluationFixtureMutation,
    FixtureMutationType,
)
from app.models.asset import Asset
from app.models.maintenance import MaintenanceRecord
from app.models.sensor import SensorReading


def _get_asset_id(
    database_session: Session,
    asset_code: str | None,
) -> int:
    if asset_code is None:
        raise ValueError("An asset-scoped fixture mutation requires an asset code.")

    asset_id = database_session.scalar(select(Asset.id).where(Asset.asset_code == asset_code))

    if asset_id is None:
        raise ValueError(f"Fixture mutation asset '{asset_code}' was not found.")

    return asset_id


def _apply_database_mutation(
    database_session: Session,
    mutation: EvaluationFixtureMutation,
) -> None:
    asset_id = _get_asset_id(
        database_session,
        mutation.asset_code,
    )

    if mutation.mutation_type == FixtureMutationType.EMPTY_SENSOR_DATA:
        database_session.execute(delete(SensorReading).where(SensorReading.asset_id == asset_id))
        return

    if mutation.mutation_type == FixtureMutationType.EMPTY_MAINTENANCE_HISTORY:
        database_session.execute(
            delete(MaintenanceRecord).where(MaintenanceRecord.asset_id == asset_id)
        )
        return

    if mutation.mutation_type == FixtureMutationType.LIMITED_MAINTENANCE_HISTORY:
        database_session.execute(
            delete(MaintenanceRecord).where(
                MaintenanceRecord.asset_id == asset_id,
                MaintenanceRecord.id.not_in(mutation.retained_maintenance_record_ids),
            )
        )
        return

    raise ValueError(f"Unsupported database fixture mutation: {mutation.mutation_type.value}.")


def _empty_engineering_documents(
    vector_client: ClientAPI,
    collection_name: str,
) -> None:
    collection = vector_client.get_collection(
        name=collection_name,
    )
    document_ids = collection.get()["ids"]

    if document_ids:
        collection.delete(ids=document_ids)


def apply_fixture_mutations(
    mutations: Sequence[EvaluationFixtureMutation],
    *,
    database_session: Session,
    vector_client: ClientAPI,
    engineering_docs_collection: str,
) -> None:
    """Apply controlled mutations to one isolated evaluation environment."""

    database_mutations = [
        mutation
        for mutation in mutations
        if mutation.mutation_type != FixtureMutationType.EMPTY_ENGINEERING_DOCUMENTS
    ]
    document_mutations = [
        mutation
        for mutation in mutations
        if mutation.mutation_type == FixtureMutationType.EMPTY_ENGINEERING_DOCUMENTS
    ]

    try:
        for mutation in database_mutations:
            _apply_database_mutation(
                database_session,
                mutation,
            )

        database_session.commit()
    except Exception:
        database_session.rollback()
        raise

    for _mutation in document_mutations:
        _empty_engineering_documents(
            vector_client,
            engineering_docs_collection,
        )
