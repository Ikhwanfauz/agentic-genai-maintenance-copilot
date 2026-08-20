from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from chromadb.api import ClientAPI
from langchain_core.tools import BaseTool, StructuredTool
from sqlalchemy.orm import Session

from app.rag.embeddings import EmbeddingProvider
from app.schemas.asset import AssetDetailsInput
from app.schemas.maintenance import MaintenanceHistoryInput
from app.schemas.rag import EngineeringDocumentSearchInput
from app.schemas.sensor import SensorAnalysisInput
from app.tools.asset import get_asset_details
from app.tools.maintenance import query_maintenance_history
from app.tools.rag import search_engineering_docs
from app.tools.sensor import analyze_sensor_data

DatabaseSessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class InvestigationToolDependencies:
    session_factory: DatabaseSessionFactory
    vector_client: ClientAPI
    embedding_provider: EmbeddingProvider
    engineering_docs_collection: str


def build_investigation_tools(
    dependencies: InvestigationToolDependencies,
) -> list[BaseTool]:
    def run_get_asset_details(**arguments: Any) -> dict[str, Any]:
        tool_input = AssetDetailsInput.model_validate(arguments)
        database_session = dependencies.session_factory()

        try:
            result = get_asset_details(database_session, tool_input)
            return result.model_dump(mode="json")
        finally:
            database_session.close()

    def run_query_maintenance_history(**arguments: Any) -> dict[str, Any]:
        tool_input = MaintenanceHistoryInput.model_validate(arguments)
        database_session = dependencies.session_factory()

        try:
            result = query_maintenance_history(database_session, tool_input)
            return result.model_dump(mode="json")
        finally:
            database_session.close()

    def run_analyze_sensor_data(**arguments: Any) -> dict[str, Any]:
        tool_input = SensorAnalysisInput.model_validate(arguments)
        database_session = dependencies.session_factory()

        try:
            result = analyze_sensor_data(database_session, tool_input)
            return result.model_dump(mode="json")
        finally:
            database_session.close()

    def run_search_engineering_docs(**arguments: Any) -> dict[str, Any]:
        tool_input = EngineeringDocumentSearchInput.model_validate(arguments)
        result = search_engineering_docs(
            dependencies.vector_client,
            dependencies.embedding_provider,
            dependencies.engineering_docs_collection,
            tool_input,
        )
        return result.model_dump(mode="json")

    return [
        StructuredTool.from_function(
            func=run_get_asset_details,
            name="get_asset_details",
            description=(
                "Retrieve deterministic details for one equipment asset, including "
                "identity, status, criticality, location, parent, and child assets. "
                "Use this near the beginning of an asset investigation."
            ),
            args_schema=AssetDetailsInput,
        ),
        StructuredTool.from_function(
            func=run_query_maintenance_history,
            name="query_maintenance_history",
            description=(
                "Retrieve deterministic maintenance-history records for one asset. "
                "Use filters only when the investigation requires a maintenance type "
                "or specific time range."
            ),
            args_schema=MaintenanceHistoryInput,
        ),
        StructuredTool.from_function(
            func=run_analyze_sensor_data,
            name="analyze_sensor_data",
            description=(
                "Analyze recent sensor readings for one asset, including data quality, "
                "summary statistics, percentage change, slope, and trend direction."
            ),
            args_schema=SensorAnalysisInput,
        ),
        StructuredTool.from_function(
            func=run_search_engineering_docs,
            name="search_engineering_docs",
            description=(
                "Semantically search indexed engineering guidance and safety documents. "
                "Returns grounded excerpts, relevance scores, and citations."
            ),
            args_schema=EngineeringDocumentSearchInput,
        ),
    ]
