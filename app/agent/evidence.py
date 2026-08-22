import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from app.schemas.asset import AssetDetailsOutput
from app.schemas.diagnosis import EvidenceSourceType
from app.schemas.evidence import CollectedEvidence
from app.schemas.maintenance import MaintenanceHistoryOutput
from app.schemas.rag import EngineeringDocumentSearchOutput
from app.schemas.sensor import SensorAnalysisOutput

EvidenceExtractor = Callable[[str, str, dict[str, Any]], list[CollectedEvidence]]


def _create_evidence(
    *,
    tool_call_id: str,
    tool_name: str,
    source_type: EvidenceSourceType,
    source_id: str,
    citation: str,
    asset_code: str | None,
    payload: BaseModel,
) -> CollectedEvidence:
    return CollectedEvidence(
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        source_type=source_type,
        source_id=source_id,
        citation=citation,
        asset_code=asset_code,
        payload=payload.model_dump(mode="json"),
    )


def _extract_asset_evidence(
    tool_call_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> list[CollectedEvidence]:
    result = AssetDetailsOutput.model_validate(content)

    return [
        _create_evidence(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            source_type=EvidenceSourceType.ASSET_DETAILS,
            source_id=result.asset_code,
            citation=f"asset:{result.asset_code}",
            asset_code=result.asset_code,
            payload=result,
        )
    ]


def _extract_maintenance_evidence(
    tool_call_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> list[CollectedEvidence]:
    result = MaintenanceHistoryOutput.model_validate(content)

    return [
        _create_evidence(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            source_type=EvidenceSourceType.MAINTENANCE_HISTORY,
            source_id=str(record.id),
            citation=f"maintenance_record:{record.id}",
            asset_code=result.asset_code,
            payload=record,
        )
        for record in result.records
    ]


def _extract_sensor_evidence(
    tool_call_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> list[CollectedEvidence]:
    result = SensorAnalysisOutput.model_validate(content)

    return [
        _create_evidence(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            source_type=EvidenceSourceType.SENSOR_ANALYSIS,
            source_id=f"{result.asset_code}:{metric.sensor_type.value}",
            citation=f"sensor:{result.asset_code}:{metric.sensor_type.value}",
            asset_code=result.asset_code,
            payload=metric,
        )
        for metric in result.metrics
    ]


def _extract_document_evidence(
    tool_call_id: str,
    tool_name: str,
    content: dict[str, Any],
) -> list[CollectedEvidence]:
    result = EngineeringDocumentSearchOutput.model_validate(content)

    return [
        _create_evidence(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            source_type=EvidenceSourceType.ENGINEERING_DOCUMENT,
            source_id=document.chunk_id,
            citation=document.citation,
            asset_code=result.asset_code,
            payload=document,
        )
        for document in result.results
    ]


EVIDENCE_EXTRACTORS: dict[str, EvidenceExtractor] = {
    "get_asset_details": _extract_asset_evidence,
    "query_maintenance_history": _extract_maintenance_evidence,
    "analyze_sensor_data": _extract_sensor_evidence,
    "search_engineering_docs": _extract_document_evidence,
}


def collect_tool_evidence(
    message: ToolMessage,
) -> list[CollectedEvidence]:
    """Convert a successful read-only tool message into typed evidence records."""

    extractor = EVIDENCE_EXTRACTORS.get(message.name or "")

    if extractor is None or getattr(message, "status", "success") == "error":
        return []

    if not isinstance(message.content, str):
        raise ValueError("Tool evidence content must be a JSON object string.")

    parsed_content = json.loads(message.content)

    if not isinstance(parsed_content, dict):
        raise ValueError("Tool evidence content must decode to a JSON object.")

    return extractor(
        message.tool_call_id,
        message.name,
        parsed_content,
    )
