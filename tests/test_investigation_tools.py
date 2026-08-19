import math
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

import chromadb
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed_reference import seed_reference_data
from app.db.seed_sensor import seed_sensor_data
from app.models.approval import Approval
from app.models.asset import Asset
from app.models.enums import SensorType
from app.models.maintenance import MaintenanceRecord
from app.models.sensor import SensorReading
from app.models.work_order import WorkOrder
from app.rag.indexer import index_engineering_documents
from app.schemas.asset import AssetDetailsInput
from app.schemas.maintenance import MaintenanceHistoryInput
from app.schemas.rag import EngineeringDocumentSearchInput
from app.schemas.sensor import (
    SensorAnalysisInput,
    TrendDirection,
)
from app.tools.asset import get_asset_details
from app.tools.maintenance import query_maintenance_history
from app.tools.rag import search_engineering_docs
from app.tools.sensor import analyze_sensor_data

REFERENCE_TIME = datetime(2026, 8, 19, tzinfo=UTC)


class IntegrationEmbeddingProvider:
    @staticmethod
    def embed_text(text: str) -> list[float]:
        normalized_text = text.lower()

        groups = (
            (
                "vibration",
                "bearing",
                "alignment",
                "coupling",
                "motor",
            ),
            (
                "flow",
                "pressure",
                "cavitation",
                "suction",
                "impeller",
            ),
            (
                "approval",
                "lockout",
                "isolation",
                "work order",
                "control",
            ),
        )

        vector = [
            float(sum(normalized_text.count(term) for term in group) + 0.1) for group in groups
        ]
        magnitude = math.sqrt(sum(value**2 for value in vector))

        return [value / magnitude for value in vector]

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_text(text)


def count_sql_rows(
    database_session: Session,
) -> dict[str, int]:
    models = {
        "assets": Asset,
        "maintenance_records": MaintenanceRecord,
        "sensor_readings": SensorReading,
        "work_orders": WorkOrder,
        "approvals": Approval,
    }

    return {
        name: int(database_session.scalar(select(func.count()).select_from(model)) or 0)
        for name, model in models.items()
    }


def test_p101_investigation_gathers_evidence_without_mutation() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as database_session:
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

        sql_counts_before = count_sql_rows(database_session)

        vector_client = chromadb.EphemeralClient()
        embedding_provider = IntegrationEmbeddingProvider()

        index_engineering_documents(
            client=vector_client,
            embedding_provider=embedding_provider,
            documents_directory=Path("data/engineering_docs"),
            collection_name="integration_engineering_docs",
        )
        vector_count_before = vector_client.get_collection(
            name="integration_engineering_docs"
        ).count()

        asset_result = get_asset_details(
            database_session,
            AssetDetailsInput(asset_code="P-101"),
        )
        maintenance_result = query_maintenance_history(
            database_session,
            MaintenanceHistoryInput(
                asset_code="P-101",
                limit=3,
            ),
        )
        sensor_result = analyze_sensor_data(
            database_session,
            SensorAnalysisInput(
                asset_code="P-101",
                sensor_types=[
                    SensorType.VIBRATION,
                    SensorType.FLOW_RATE,
                ],
            ),
        )
        document_result = search_engineering_docs(
            client=vector_client,
            embedding_provider=embedding_provider,
            collection_name="integration_engineering_docs",
            tool_input=EngineeringDocumentSearchInput(
                query=("increasing pump vibration with possible coupling alignment issue"),
                asset_code="P-101",
                top_k=3,
                minimum_relevance=0.0,
            ),
        )

        vibration_metric = next(
            metric for metric in sensor_result.metrics if metric.sensor_type == SensorType.VIBRATION
        )
        flow_metric = next(
            metric for metric in sensor_result.metrics if metric.sensor_type == SensorType.FLOW_RATE
        )

        assert asset_result.criticality.value == "critical"
        assert asset_result.child_asset_codes == ["M-101"]

        assert maintenance_result.total_matching_records == 3
        assert maintenance_result.records[0].summary == ("Routine vibration inspection")

        assert vibration_metric.trend == (TrendDirection.INCREASING)
        assert flow_metric.trend == (TrendDirection.DECREASING)

        assert document_result.returned_result_count == 3
        assert any(
            result.section
            in {
                "Elevated Vibration",
                "Correlated Pump and Motor Vibration",
            }
            for result in document_result.results
        )
        assert all(result.citation for result in document_result.results)

        sql_counts_after = count_sql_rows(database_session)
        vector_count_after = vector_client.get_collection(
            name="integration_engineering_docs"
        ).count()

        assert sql_counts_after == sql_counts_before
        assert vector_count_after == vector_count_before
