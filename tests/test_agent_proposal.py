from collections.abc import Generator
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

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
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
    RecommendedAction,
)
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    GroundingDecision,
)


@pytest.fixture
def database_session_factory() -> Generator[
    sessionmaker[Session],
    None,
    None,
]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
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

    try:
        yield factory
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def create_diagnosis(
    *,
    actions: list[RecommendedAction] | None = None,
) -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary=("Evidence supports a developing mechanical vibration issue."),
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale=("Sensor evidence supports controlled physical inspection."),
        likely_causes=["Developing coupling alignment or bearing condition issue"],
        evidence=[
            EvidenceReference(
                source_type=(EvidenceSourceType.SENSOR_ANALYSIS),
                source_id="P-101:vibration",
                summary=("Vibration increased during the analysis window."),
                citation="sensor:P-101:vibration",
            )
        ],
        recommended_actions=(
            actions
            if actions is not None
            else [
                RecommendedAction(
                    action=("Inspect pump bearings and coupling alignment."),
                    rationale=("The vibration trend requires controlled physical inspection."),
                    priority=WorkOrderPriority.HIGH,
                    state_changing=True,
                    requires_human_approval=True,
                )
            ]
        ),
        safety_notes=["Use approved isolation procedures before inspection."],
    )


def create_grounding_result() -> DiagnosisGroundingResult:
    return DiagnosisGroundingResult(
        decision=GroundingDecision.GROUNDED,
        original_outcome=InvestigationOutcome.DIAGNOSIS.value,
        final_outcome=InvestigationOutcome.DIAGNOSIS.value,
        matched_citations=["sensor:P-101:vibration"],
        violations=[],
        downgraded=False,
    )


def create_proposal_state():
    state = create_initial_state(
        "Investigate elevated P-101 vibration",
        "P-101",
        run_id="run-proposal-001",
        thread_id="thread-proposal-001",
    )
    state["diagnosis"] = create_diagnosis()
    state["grounding_result"] = create_grounding_result()

    return state


def row_count(
    factory: sessionmaker[Session],
    model: type[object],
) -> int:
    with factory() as database_session:
        return int(database_session.scalar(select(func.count()).select_from(model)) or 0)


def test_proposal_node_persists_highest_priority_action(
    database_session_factory: sessionmaker[Session],
) -> None:
    factory = database_session_factory
    number_factory = Mock(return_value="WO-PROP-NODE-001")
    state = create_proposal_state()
    state["diagnosis"] = create_diagnosis(
        actions=[
            RecommendedAction(
                action="Review vibration trend.",
                rationale="Additional review may support planning.",
                priority=WorkOrderPriority.MEDIUM,
                state_changing=False,
                requires_human_approval=False,
            ),
            RecommendedAction(
                action="Inspect pump bearings and coupling alignment.",
                rationale=("The grounded evidence supports physical inspection."),
                priority=WorkOrderPriority.HIGH,
                state_changing=True,
                requires_human_approval=True,
            ),
            RecommendedAction(
                action="Perform controlled urgent pump inspection.",
                rationale=("Critical evidence requires urgent human-reviewed work."),
                priority=WorkOrderPriority.CRITICAL,
                state_changing=True,
                requires_human_approval=True,
            ),
        ]
    )
    node = create_propose_work_order_node(
        factory,
        work_order_number_factory=number_factory,
    )

    result = node(state)

    assert result["status"] == AgentStatus.RUNNING
    assert result["route"] == AgentRoute.APPROVAL
    assert result["work_order_proposal"] is not None
    assert result["work_order_proposal"].priority == WorkOrderPriority.CRITICAL
    assert result["work_order_proposal"].title == (
        "P-101: Perform controlled urgent pump inspection."
    )
    assert result["work_order_proposal"].status == WorkOrderStatus.PENDING_APPROVAL
    assert result["work_order_proposal"].approval_decision == ApprovalDecision.PENDING
    assert row_count(factory, WorkOrder) == 1
    assert row_count(factory, Approval) == 1
    number_factory.assert_called_once()


def test_proposal_node_retry_is_idempotent(
    database_session_factory: sessionmaker[Session],
) -> None:
    factory = database_session_factory
    number_factory = Mock(return_value="WO-PROP-NODE-002")
    node = create_propose_work_order_node(
        factory,
        work_order_number_factory=number_factory,
    )
    state = create_proposal_state()

    first_result = node(state)
    second_result = node(state)

    assert first_result["work_order_proposal"].created_new is True
    assert second_result["work_order_proposal"].created_new is False
    assert (
        second_result["work_order_proposal"].work_order_id
        == first_result["work_order_proposal"].work_order_id
    )
    assert row_count(factory, WorkOrder) == 1
    assert row_count(factory, Approval) == 1
    assert number_factory.call_count == 1


def test_proposal_node_skips_when_no_action_requires_approval(
    database_session_factory: sessionmaker[Session],
) -> None:
    factory = database_session_factory
    state = create_proposal_state()
    state["diagnosis"] = create_diagnosis(
        actions=[
            RecommendedAction(
                action="Continue monitoring vibration trend.",
                rationale="No physical intervention is currently required.",
                priority=WorkOrderPriority.MEDIUM,
                state_changing=False,
                requires_human_approval=False,
            )
        ]
    )
    node = create_propose_work_order_node(factory)

    result = node(state)

    assert result["status"] == AgentStatus.COMPLETED
    assert result["route"] == AgentRoute.END
    assert result["work_order_proposal"] is None
    assert result["error"] is None
    assert row_count(factory, WorkOrder) == 0
    assert row_count(factory, Approval) == 0


def test_proposal_node_rejects_ungrounded_diagnosis(
    database_session_factory: sessionmaker[Session],
) -> None:
    factory = database_session_factory
    state = create_proposal_state()
    state["grounding_result"] = DiagnosisGroundingResult(
        decision=GroundingDecision.ABSTAINED,
        original_outcome=InvestigationOutcome.DIAGNOSIS.value,
        final_outcome=(InvestigationOutcome.INSUFFICIENT_EVIDENCE.value),
        matched_citations=[],
        violations=["Evidence coverage is incomplete."],
        downgraded=True,
    )
    node = create_propose_work_order_node(factory)

    result = node(state)

    assert result["status"] == AgentStatus.FAILED
    assert result["route"] == AgentRoute.END
    assert result["work_order_proposal"] is None
    assert "Only a grounded completed diagnosis" in result["error"]
    assert row_count(factory, WorkOrder) == 0
    assert row_count(factory, Approval) == 0
