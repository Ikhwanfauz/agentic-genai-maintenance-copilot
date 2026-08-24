from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage
from langgraph.types import Command
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.agent.checkpoint import open_sqlite_checkpointer
from app.agent.graph import build_agent_graph
from app.agent.proposal import create_propose_work_order_node
from app.agent.state import (
    AgentRoute,
    AgentStatus,
    create_initial_state,
)
from app.db.base import Base
from app.db.session import create_database_engine
from app.models.approval import Approval
from app.models.asset import Asset
from app.models.enums import (
    ApprovalDecision,
    AssetStatus,
    AssetType,
    Criticality,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.models.work_order import WorkOrder
from app.schemas.actions import (
    WorkOrderApprovalDecisionInput,
)
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
    RecommendedAction,
)
from app.schemas.evidence import CollectedEvidence
from app.schemas.hitl import WorkOrderApprovalResume
from app.services.approvals import decide_work_order_approval


def create_application_database(
    database_path: Path,
) -> tuple[
    Engine,
    sessionmaker[Session],
]:
    engine = create_database_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )

    with factory() as database_session:
        database_session.add(
            Asset(
                asset_code="P-101",
                name="Main Cooling Water Pump",
                asset_type=AssetType.PUMP,
                status=AssetStatus.OPERATIONAL,
                criticality=Criticality.CRITICAL,
                location="Cooling Water Area",
            )
        )
        database_session.commit()

    return engine, factory


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
            tool_call_id=f"e2e-call-{index}",
            tool_name="e2e_test_tool",
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
        summary=("Evidence supports a developing mechanical vibration issue."),
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale=(
            "Asset, maintenance, sensor, and engineering evidence support controlled inspection."
        ),
        likely_causes=["Developing coupling alignment or bearing condition issue"],
        evidence=[
            EvidenceReference(
                source_type=evidence.source_type,
                source_id=evidence.source_id,
                summary=(f"Grounded {evidence.source_type.value} evidence."),
                citation=evidence.citation,
            )
            for evidence in ledger
        ],
        recommended_actions=[
            RecommendedAction(
                action=("Inspect pump bearings and coupling alignment."),
                rationale=(
                    "The grounded vibration evidence requires controlled physical inspection."
                ),
                priority=WorkOrderPriority.HIGH,
                state_changing=True,
                requires_human_approval=True,
            )
        ],
        safety_notes=[
            "Use approved isolation procedures before inspection.",
            "The copilot must not control machinery or PLCs.",
        ],
    )


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (
            ApprovalDecision.APPROVED,
            WorkOrderStatus.APPROVED,
        ),
        (
            ApprovalDecision.REJECTED,
            WorkOrderStatus.REJECTED,
        ),
    ],
)
def test_grounded_work_order_completes_human_approval_journey(
    tmp_path: Path,
    decision: ApprovalDecision,
    expected_status: WorkOrderStatus,
) -> None:
    application_database_path = tmp_path / "maintenance_copilot.sqlite"
    checkpoint_path = tmp_path / "langgraph_checkpoints.sqlite"
    engine, session_factory = create_application_database(application_database_path)

    run_id = f"e2e-run-{decision.value}"
    thread_id = f"e2e-thread-{decision.value}"
    ledger = create_complete_evidence_ledger()

    investigation_model = Mock()
    investigation_model.invoke.return_value = AIMessage(
        content="All required evidence categories are available."
    )
    diagnosis_model = Mock()
    diagnosis_model.invoke.return_value = create_grounded_diagnosis(ledger)
    number_factory = Mock(return_value=(f"WO-E2E-{decision.value.upper()}"))
    proposal_node = create_propose_work_order_node(
        session_factory,
        work_order_number_factory=number_factory,
    )
    state = create_initial_state(
        "Investigate elevated P-101 vibration",
        "P-101",
        run_id=run_id,
        thread_id=thread_id,
    )
    state["evidence_ledger"] = ledger
    config = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    try:
        with open_sqlite_checkpointer(checkpoint_path) as first_checkpointer:
            first_graph = build_agent_graph(
                investigation_model,
                diagnosis_model=diagnosis_model,
                proposal_node=proposal_node,
                checkpointer=first_checkpointer,
            )
            interrupted = first_graph.invoke(
                state,
                config=config,
            )

        proposal = interrupted["work_order_proposal"]

        assert interrupted["status"] == (AgentStatus.WAITING_FOR_APPROVAL)
        assert interrupted["route"] == AgentRoute.APPROVAL
        assert proposal is not None
        assert proposal.created_new is True
        assert proposal.status == (WorkOrderStatus.PENDING_APPROVAL)
        assert proposal.approval_decision == (ApprovalDecision.PENDING)
        assert len(interrupted["__interrupt__"]) == 1

        decision_reason = (
            "Inspection plan reviewed and approved."
            if decision == ApprovalDecision.APPROVED
            else "Work scope requires further technical review."
        )

        with session_factory() as database_session:
            decision_output = decide_work_order_approval(
                database_session,
                WorkOrderApprovalDecisionInput(
                    work_order_id=proposal.work_order_id,
                    request_version=proposal.request_version,
                    decision=decision,
                    decided_by="technician-001",
                    decision_reason=decision_reason,
                    decision_source="human",
                    approval_scope=proposal.approval_scope,
                ),
                decision_clock=lambda: datetime(
                    2026,
                    8,
                    24,
                    14,
                    0,
                    tzinfo=UTC,
                ),
            )

        assert decision_output.work_order_status == (expected_status)
        assert decision_output.decision == decision

        resume_payload = WorkOrderApprovalResume(
            run_id=run_id,
            thread_id=thread_id,
            decision=decision_output,
        )

        with open_sqlite_checkpointer(checkpoint_path) as reopened_checkpointer:
            reopened_graph = build_agent_graph(
                investigation_model,
                diagnosis_model=diagnosis_model,
                proposal_node=proposal_node,
                checkpointer=reopened_checkpointer,
            )
            resumed = reopened_graph.invoke(
                Command(
                    resume=resume_payload.model_dump(mode="json"),
                ),
                config=config,
            )

        assert resumed["status"] == AgentStatus.COMPLETED
        assert resumed["route"] == AgentRoute.END
        assert resumed["approval_decision"] is not None
        assert resumed["approval_decision"].decision == decision
        assert resumed["approval_decision"].work_order_status == expected_status
        assert "__interrupt__" not in resumed

        assert investigation_model.invoke.call_count == 1
        assert diagnosis_model.invoke.call_count == 1
        assert number_factory.call_count == 1

        with session_factory() as database_session:
            work_order = database_session.get(
                WorkOrder,
                proposal.work_order_id,
            )
            approval = database_session.get(
                Approval,
                proposal.approval_id,
            )

            assert work_order is not None
            assert approval is not None
            assert work_order.status == expected_status
            assert approval.decision == decision
            assert approval.decided_by == "technician-001"
            assert approval.decision_reason == decision_reason

            assert work_order.executed_at is None
            assert work_order.execution_summary is None
            assert approval.consumed_at is None
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
