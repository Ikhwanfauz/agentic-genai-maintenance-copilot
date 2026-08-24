from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agent.graph import build_agent_graph
from app.agent.state import (
    AgentRoute,
    AgentState,
    AgentStatus,
    create_initial_state,
)
from app.models.enums import (
    ApprovalDecision,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.schemas.actions import (
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.evidence import CollectedEvidence
from app.schemas.hitl import WorkOrderApprovalResume


def create_complete_evidence_ledger() -> list[CollectedEvidence]:
    evidence_details = [
        (
            EvidenceSourceType.ASSET_DETAILS,
            "P-101",
            "asset:P-101",
        ),
        (
            EvidenceSourceType.MAINTENANCE_HISTORY,
            "7",
            "maintenance_record:7",
        ),
        (
            EvidenceSourceType.SENSOR_ANALYSIS,
            "P-101:vibration",
            "sensor:P-101:vibration",
        ),
        (
            EvidenceSourceType.ENGINEERING_DOCUMENT,
            "ENG-PUMP-001:elevated-vibration",
            (
                "ENG-PUMP-001 | Elevated Vibration | "
                "data/engineering_docs/pump_troubleshooting_guide.md"
            ),
        ),
    ]

    return [
        CollectedEvidence(
            tool_call_id=f"call-{index}",
            tool_name="test_tool",
            source_type=source_type,
            source_id=source_id,
            citation=citation,
            asset_code="P-101",
            payload={"source_id": source_id},
        )
        for index, (
            source_type,
            source_id,
            citation,
        ) in enumerate(
            evidence_details,
            start=1,
        )
    ]


def create_grounded_diagnosis(
    ledger: list[CollectedEvidence],
) -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary="Evidence supports a developing mechanical vibration issue.",
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale=(
            "Asset, maintenance, sensor, and engineering evidence are available."
        ),
        likely_causes=["Developing coupling alignment or bearing condition issue"],
        evidence=[
            EvidenceReference(
                source_type=evidence.source_type,
                source_id=evidence.source_id,
                summary=f"Grounded evidence from {evidence.source_type.value}.",
                citation=evidence.citation,
            )
            for evidence in ledger
        ],
        recommended_actions=[],
        safety_notes=["Use approved isolation procedures before physical inspection."],
    )


def create_pending_proposal() -> WorkOrderProposalOutput:
    return WorkOrderProposalOutput(
        work_order_id=10,
        work_order_number="WO-PROP-0010",
        asset_code="P-101",
        title="Inspect elevated P-101 vibration",
        description=("Inspect pump bearings, coupling alignment, and lubrication condition."),
        priority=WorkOrderPriority.HIGH,
        status=WorkOrderStatus.PENDING_APPROVAL,
        revision=1,
        proposed_by="maintenance-agent",
        idempotency_key="p101-vibration-run-001",
        approval_id=5,
        approval_decision=ApprovalDecision.PENDING,
        request_version=1,
        approval_scope="execute_work_order",
        created_new=True,
    )


def create_approval_resume() -> WorkOrderApprovalResume:
    return WorkOrderApprovalResume(
        run_id="run-001",
        thread_id="thread-001",
        decision=WorkOrderApprovalDecisionOutput(
            work_order_id=10,
            work_order_number="WO-PROP-0010",
            approval_id=5,
            request_version=1,
            decision=ApprovalDecision.APPROVED,
            work_order_status=WorkOrderStatus.APPROVED,
            decided_by="technician-001",
            decided_at=datetime(2026, 8, 24, 11, 0, tzinfo=UTC),
            decision_reason="Inspection plan reviewed and approved.",
            approval_scope="execute_work_order",
            decision_applied=True,
        ),
    )


def test_main_agent_graph_pauses_and_resumes_after_grounded_proposal() -> None:
    ledger = create_complete_evidence_ledger()

    investigation_model = Mock()
    investigation_model.invoke.return_value = AIMessage(content="Evidence collection is complete.")
    diagnosis_model = Mock()
    diagnosis_model.invoke.return_value = create_grounded_diagnosis(ledger)
    proposal_call = Mock()

    def proposal_node(
        state: AgentState,
    ) -> dict[str, object]:
        proposal_call(state)

        return {
            "work_order_proposal": create_pending_proposal(),
            "visited_nodes": ["propose_work_order"],
        }

    graph = build_agent_graph(
        investigation_model,
        diagnosis_model=diagnosis_model,
        proposal_node=proposal_node,
        checkpointer=InMemorySaver(),
    )
    state = create_initial_state(
        "Investigate elevated P-101 vibration",
        "P-101",
        run_id="run-001",
        thread_id="thread-001",
    )
    state["evidence_ledger"] = ledger
    config = {
        "configurable": {
            "thread_id": state["thread_id"],
        }
    }

    interrupted = graph.invoke(
        state,
        config=config,
    )

    assert interrupted["status"] == AgentStatus.WAITING_FOR_APPROVAL
    assert interrupted["route"] == AgentRoute.APPROVAL
    assert interrupted["work_order_proposal"] is not None
    assert len(interrupted["__interrupt__"]) == 1
    assert proposal_call.call_count == 1

    proposal_state = proposal_call.call_args.args[0]

    assert proposal_state["grounding_result"].decision == "grounded"
    assert proposal_state["diagnosis"].outcome == InvestigationOutcome.DIAGNOSIS

    resumed = graph.invoke(
        Command(
            resume=create_approval_resume().model_dump(mode="json"),
        ),
        config=config,
    )

    assert resumed["status"] == AgentStatus.COMPLETED
    assert resumed["route"] == AgentRoute.END
    assert resumed["approval_decision"] is not None
    assert resumed["approval_decision"].decision == ApprovalDecision.APPROVED
    assert resumed["visited_nodes"] == [
        "initialize",
        "mark_ready",
        "call_model",
        "synthesize_diagnosis",
        "propose_work_order",
        "prepare_approval_pause",
        "await_work_order_approval",
    ]
    assert investigation_model.invoke.call_count == 1
    assert diagnosis_model.invoke.call_count == 1
    assert proposal_call.call_count == 1


def test_main_agent_graph_skips_proposal_for_ungrounded_diagnosis() -> None:
    investigation_model = Mock()
    investigation_model.invoke.return_value = AIMessage(
        content="No grounded evidence is available."
    )
    diagnosis_model = Mock()
    diagnosis_model.invoke.return_value = create_grounded_diagnosis(
        create_complete_evidence_ledger()
    )
    proposal_call = Mock()

    def proposal_node(
        state: AgentState,
    ) -> dict[str, object]:
        proposal_call(state)

        return {
            "work_order_proposal": create_pending_proposal(),
        }

    graph = build_agent_graph(
        investigation_model,
        diagnosis_model=diagnosis_model,
        proposal_node=proposal_node,
        checkpointer=InMemorySaver(),
    )
    state = create_initial_state(
        "Investigate P-101 vibration",
        "P-101",
        run_id="run-ungrounded",
        thread_id="thread-ungrounded",
    )
    config = {
        "configurable": {
            "thread_id": state["thread_id"],
        }
    }

    result = graph.invoke(
        state,
        config=config,
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert result["route"] == AgentRoute.END
    assert result["diagnosis"].outcome == (InvestigationOutcome.INSUFFICIENT_EVIDENCE)
    assert result["grounding_result"].downgraded is True
    assert result["work_order_proposal"] is None
    assert "__interrupt__" not in result
    proposal_call.assert_not_called()


def test_proposal_node_requires_diagnosis_model_and_checkpointer() -> None:
    model = Mock()

    def proposal_node(
        _state: AgentState,
    ) -> dict[str, object]:
        return {
            "work_order_proposal": create_pending_proposal(),
        }

    with pytest.raises(
        ValueError,
        match="requires a diagnosis model",
    ):
        build_agent_graph(
            model,
            proposal_node=proposal_node,
            checkpointer=InMemorySaver(),
        )

    with pytest.raises(
        ValueError,
        match="requires a LangGraph checkpointer",
    ):
        build_agent_graph(
            model,
            diagnosis_model=Mock(),
            proposal_node=proposal_node,
        )
