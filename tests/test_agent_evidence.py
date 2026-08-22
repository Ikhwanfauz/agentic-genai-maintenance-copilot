from datetime import UTC, date, datetime

from langchain_core.messages import ToolMessage

from app.agent.evidence import collect_tool_evidence
from app.models.enums import (
    AssetStatus,
    AssetType,
    Criticality,
    MaintenanceType,
    SensorType,
)
from app.schemas.asset import AssetDetailsOutput
from app.schemas.diagnosis import EvidenceSourceType
from app.schemas.maintenance import (
    MaintenanceHistoryOutput,
    MaintenanceRecordOutput,
)
from app.schemas.rag import (
    EngineeringDocumentResult,
    EngineeringDocumentSearchOutput,
)
from app.schemas.sensor import (
    DataQualitySummary,
    SensorAnalysisOutput,
    SensorMetricOutput,
    TrendDirection,
)

REFERENCE_TIME = datetime(2026, 8, 19, tzinfo=UTC)


def create_tool_message(
    name: str,
    output,
    *,
    tool_call_id: str = "tool-call-1",
) -> ToolMessage:
    return ToolMessage(
        content=output.model_dump_json(),
        name=name,
        tool_call_id=tool_call_id,
    )


def test_collects_asset_evidence_with_application_citation() -> None:
    output = AssetDetailsOutput(
        id=1,
        asset_code="P-101",
        name="Main Cooling Water Pump",
        asset_type=AssetType.PUMP,
        status=AssetStatus.OPERATIONAL,
        criticality=Criticality.CRITICAL,
        location="Utilities Area",
        manufacturer="FlowServe Simulation",
        model_number="CS-200",
        installation_date=date(2021, 6, 15),
        description="Synthetic main cooling-water pump.",
        parent_asset_code=None,
        child_asset_codes=["M-101"],
    )

    evidence = collect_tool_evidence(create_tool_message("get_asset_details", output))

    assert len(evidence) == 1
    assert evidence[0].source_type == EvidenceSourceType.ASSET_DETAILS
    assert evidence[0].source_id == "P-101"
    assert evidence[0].citation == "asset:P-101"
    assert evidence[0].payload["criticality"] == "critical"


def test_collects_one_evidence_record_per_maintenance_record() -> None:
    output = MaintenanceHistoryOutput(
        asset_code="P-101",
        total_matching_records=1,
        returned_record_count=1,
        has_more=False,
        records=[
            MaintenanceRecordOutput(
                id=7,
                performed_at=REFERENCE_TIME,
                maintenance_type=MaintenanceType.PREDICTIVE,
                summary="Routine vibration inspection",
                findings="Vibration increased from the previous route.",
                action_taken="Requested follow-up investigation.",
                technician="A. Rahman",
                downtime_hours=0.0,
            )
        ],
    )

    evidence = collect_tool_evidence(create_tool_message("query_maintenance_history", output))

    assert len(evidence) == 1
    assert evidence[0].source_type == EvidenceSourceType.MAINTENANCE_HISTORY
    assert evidence[0].source_id == "7"
    assert evidence[0].citation == "maintenance_record:7"
    assert evidence[0].asset_code == "P-101"


def test_collects_one_evidence_record_per_sensor_metric() -> None:
    output = SensorAnalysisOutput(
        asset_code="P-101",
        analysis_start=REFERENCE_TIME,
        analysis_end=REFERENCE_TIME,
        lookback_hours=168,
        trend_threshold_percent=5.0,
        quality=DataQualitySummary(
            total_readings=168,
            analyzed_readings=168,
            excluded_readings=0,
            good_readings=168,
            suspect_readings=0,
            bad_readings=0,
        ),
        metrics=[
            SensorMetricOutput(
                sensor_type=SensorType.VIBRATION,
                unit="mm/s",
                reading_count=168,
                first_recorded_at=REFERENCE_TIME,
                latest_recorded_at=REFERENCE_TIME,
                minimum=2.1,
                maximum=5.8,
                mean=3.7,
                first_window_mean=2.4,
                latest_window_mean=5.1,
                absolute_change=2.7,
                percentage_change=112.5,
                slope_per_hour=0.02,
                trend=TrendDirection.INCREASING,
            )
        ],
    )

    evidence = collect_tool_evidence(create_tool_message("analyze_sensor_data", output))

    assert len(evidence) == 1
    assert evidence[0].source_type == EvidenceSourceType.SENSOR_ANALYSIS
    assert evidence[0].source_id == "P-101:vibration"
    assert evidence[0].citation == "sensor:P-101:vibration"
    assert evidence[0].payload["trend"] == "increasing"


def test_preserves_engineering_document_citation() -> None:
    citation = (
        "ENG-PUMP-001 | Elevated Vibration | data/engineering_docs/pump_troubleshooting_guide.md"
    )
    output = EngineeringDocumentSearchOutput(
        query="increasing pump vibration",
        asset_code="P-101",
        returned_result_count=1,
        results=[
            EngineeringDocumentResult(
                chunk_id="ENG-PUMP-001:elevated-vibration",
                document_id="ENG-PUMP-001",
                title="Centrifugal Pump Troubleshooting Guide",
                section="Elevated Vibration",
                source_path="data/engineering_docs/pump_troubleshooting_guide.md",
                applicable_assets="P-101, P-102, P-201",
                content="Check alignment and bearing condition.",
                distance=0.1,
                relevance_score=0.909091,
                citation=citation,
            )
        ],
    )

    evidence = collect_tool_evidence(create_tool_message("search_engineering_docs", output))

    assert len(evidence) == 1
    assert evidence[0].source_type == EvidenceSourceType.ENGINEERING_DOCUMENT
    assert evidence[0].source_id == "ENG-PUMP-001:elevated-vibration"
    assert evidence[0].citation == citation


def test_does_not_collect_failed_tool_output() -> None:
    message = ToolMessage(
        content="Error: asset not found",
        name="get_asset_details",
        tool_call_id="failed-call",
        status="error",
    )

    assert collect_tool_evidence(message) == []
