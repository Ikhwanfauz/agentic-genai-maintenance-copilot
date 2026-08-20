from unittest.mock import Mock

from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from app.agent.graph import build_agent_graph
from app.agent.state import AgentRoute, AgentStatus, create_initial_state
from app.agent.synthesis import bind_diagnosis_output
from app.models.enums import WorkOrderPriority
from app.schemas.asset import AssetDetailsInput
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
    RecommendedAction,
)


def create_asset_tool() -> StructuredTool:
    def get_asset_details(asset_code: str) -> dict[str, object]:
        return {
            "asset_code": asset_code,
            "name": "Main Cooling Water Pump",
            "criticality": "critical",
        }

    return StructuredTool.from_function(
        func=get_asset_details,
        name="get_asset_details",
        description="Retrieve details for one maintenance asset.",
        args_schema=AssetDetailsInput,
    )


def create_diagnosis() -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary="P-101 requires further vibration investigation.",
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale=(
            "Asset evidence is available, but sensor and maintenance evidence is still limited."
        ),
        likely_causes=["Developing mechanical vibration issue"],
        evidence=[
            EvidenceReference(
                source_type=EvidenceSourceType.ASSET_DETAILS,
                source_id="P-101",
                summary="P-101 is a critical cooling-water pump.",
                citation="asset:P-101",
            )
        ],
        recommended_actions=[
            RecommendedAction(
                action="Gather vibration and maintenance-history evidence.",
                rationale="Additional evidence is required before physical work.",
                priority=WorkOrderPriority.HIGH,
                state_changing=False,
                requires_human_approval=False,
            )
        ],
        safety_notes=["Do not perform direct machine-control actions through the copilot."],
    )


def test_agent_stores_valid_structured_diagnosis() -> None:
    investigation_model = Mock()
    investigation_model.invoke.side_effect = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "get_asset_details",
                    "args": {"asset_code": "P-101"},
                    "id": "asset-call-1",
                    "type": "tool_call",
                }
            ],
        ),
        AIMessage(content="Asset evidence gathered."),
    ]
    diagnosis_model = Mock()
    diagnosis_model.invoke.return_value = create_diagnosis()

    graph = build_agent_graph(
        investigation_model,
        [create_asset_tool()],
        diagnosis_model=diagnosis_model,
    )
    result = graph.invoke(
        create_initial_state(
            "Investigate vibration on P-101",
            "P-101",
            max_iterations=3,
        )
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert result["route"] == AgentRoute.END
    assert isinstance(result["diagnosis"], MaintenanceDiagnosis)
    assert result["diagnosis"].asset_code == "P-101"
    assert result["visited_nodes"] == [
        "initialize",
        "mark_ready",
        "call_model",
        "execute_tools",
        "call_model",
        "synthesize_diagnosis",
    ]
    assert investigation_model.invoke.call_count == 2
    diagnosis_model.invoke.assert_called_once()


def test_agent_rejects_invalid_structured_diagnosis() -> None:
    investigation_model = Mock()
    investigation_model.invoke.return_value = AIMessage(content="No additional tools requested.")
    diagnosis_model = Mock()
    diagnosis_model.invoke.return_value = {
        "asset_code": "P-101",
        "outcome": "diagnosis",
        "summary": "Invalid diagnosis without required grounded fields.",
    }

    graph = build_agent_graph(
        investigation_model,
        diagnosis_model=diagnosis_model,
    )
    result = graph.invoke(
        create_initial_state(
            "Investigate P-101",
            "P-101",
        )
    )

    assert result["status"] == AgentStatus.FAILED
    assert result["route"] == AgentRoute.END
    assert result["diagnosis"] is None
    assert "Structured diagnosis validation failed" in result["error"]


def test_bind_diagnosis_output_uses_pydantic_schema() -> None:
    model = Mock()
    structured_model = Mock()
    model.with_structured_output.return_value = structured_model

    result = bind_diagnosis_output(model)

    assert result is structured_model
    model.with_structured_output.assert_called_once_with(
        MaintenanceDiagnosis,
        method="json_schema",
    )
