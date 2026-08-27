from collections.abc import Generator
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
from app.schemas.actions import WorkOrderProposalInput
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    GroundingDecision,
)
from app.services.exceptions import (
    WorkOrderAssetNotFoundError,
    WorkOrderIdempotencyConflictError,
)
from app.services.work_orders import propose_work_order


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        session.add(
            Asset(
                asset_code="P-101",
                name="Main Cooling Water Pump",
                asset_type=AssetType.PUMP,
                status=AssetStatus.OPERATIONAL,
                criticality=Criticality.CRITICAL,
                location="Cooling Water Area",
            )
        )
        session.commit()

        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def create_diagnosis(
    asset_code: str = "P-101",
) -> MaintenanceDiagnosis:
    citation = f"sensor:{asset_code}:vibration"

    return MaintenanceDiagnosis(
        asset_code=asset_code,
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary="Evidence supports a developing vibration condition.",
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale=("Sensor evidence supports physical inspection."),
        likely_causes=["Developing coupling alignment or bearing condition issue"],
        evidence=[
            EvidenceReference(
                source_type=EvidenceSourceType.SENSOR_ANALYSIS,
                source_id=f"{asset_code}:vibration",
                summary="Vibration increased during the analysis window.",
                citation=citation,
            )
        ],
        recommended_actions=[],
        safety_notes=["Use approved isolation procedures before inspection."],
    )


def create_grounding_result(
    asset_code: str = "P-101",
) -> DiagnosisGroundingResult:
    return DiagnosisGroundingResult(
        decision=GroundingDecision.GROUNDED,
        original_outcome=InvestigationOutcome.DIAGNOSIS.value,
        final_outcome=InvestigationOutcome.DIAGNOSIS.value,
        matched_citations=[f"sensor:{asset_code}:vibration"],
        violations=[],
        downgraded=False,
    )


def create_proposal_input(
    *,
    asset_code: str = "P-101",
    idempotency_key: str = "p101-vibration-run-001",
    title: str = "Inspect elevated P-101 vibration",
) -> WorkOrderProposalInput:
    return WorkOrderProposalInput(
        asset_code=asset_code,
        title=title,
        description=("Inspect pump bearings, coupling alignment, and lubrication condition."),
        priority=WorkOrderPriority.HIGH,
        proposed_by="maintenance-agent",
        idempotency_key=idempotency_key,
        source_run_id="run-001",
        diagnosis=create_diagnosis(asset_code),
        grounding_result=create_grounding_result(asset_code),
        requires_human_approval=True,
    )


def row_count(
    database_session: Session,
    model: type[object],
) -> int:
    return int(database_session.scalar(select(func.count()).select_from(model)) or 0)


def test_proposal_creates_work_order_and_pending_approval(
    database_session: Session,
) -> None:
    result = propose_work_order(
        database_session,
        create_proposal_input(),
        work_order_number_factory=lambda: "WO-PROP-TEST-0001",
    )

    assert result.created_new is True
    assert result.work_order_number == "WO-PROP-TEST-0001"
    assert result.asset_code == "P-101"
    assert result.status == WorkOrderStatus.PENDING_APPROVAL
    assert result.approval_decision == ApprovalDecision.PENDING
    assert result.request_version == 1
    assert row_count(database_session, WorkOrder) == 1
    assert row_count(database_session, Approval) == 1

    work_order = database_session.get(
        WorkOrder,
        result.work_order_id,
    )
    approval = database_session.get(
        Approval,
        result.approval_id,
    )

    assert work_order is not None
    assert approval is not None
    assert approval.work_order_id == work_order.id
    assert approval.request_version == work_order.revision


def test_identical_retry_returns_existing_proposal(
    database_session: Session,
) -> None:
    number_factory = Mock(return_value="WO-PROP-TEST-0002")
    proposal = create_proposal_input()

    first_result = propose_work_order(
        database_session,
        proposal,
        work_order_number_factory=number_factory,
    )
    second_result = propose_work_order(
        database_session,
        proposal,
        work_order_number_factory=number_factory,
    )

    assert first_result.created_new is True
    assert second_result.created_new is False
    assert second_result.work_order_id == first_result.work_order_id
    assert second_result.approval_id == first_result.approval_id
    assert number_factory.call_count == 1
    assert row_count(database_session, WorkOrder) == 1
    assert row_count(database_session, Approval) == 1


def test_reused_key_with_different_payload_is_rejected(
    database_session: Session,
) -> None:
    propose_work_order(
        database_session,
        create_proposal_input(),
        work_order_number_factory=lambda: "WO-PROP-TEST-0003",
    )

    with pytest.raises(
        WorkOrderIdempotencyConflictError,
        match="different work-order proposal",
    ):
        propose_work_order(
            database_session,
            create_proposal_input(
                title="Inspect a different P-101 condition",
            ),
        )

    assert row_count(database_session, WorkOrder) == 1
    assert row_count(database_session, Approval) == 1


def test_unknown_asset_rolls_back_without_records(
    database_session: Session,
) -> None:
    with pytest.raises(
        WorkOrderAssetNotFoundError,
        match="P-999",
    ):
        propose_work_order(
            database_session,
            create_proposal_input(
                asset_code="P-999",
                idempotency_key="p999-vibration-run-001",
                title="Inspect elevated P-999 vibration",
            ),
        )

    assert row_count(database_session, WorkOrder) == 0
    assert row_count(database_session, Approval) == 0
