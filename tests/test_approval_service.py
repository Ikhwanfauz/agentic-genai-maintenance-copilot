from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
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
from app.schemas.actions import WorkOrderApprovalDecisionInput
from app.services.approvals import decide_work_order_approval
from app.services.exceptions import WorkOrderApprovalConflictError


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        asset = Asset(
            asset_code="P-101",
            name="Main Cooling Water Pump",
            asset_type=AssetType.PUMP,
            status=AssetStatus.OPERATIONAL,
            criticality=Criticality.CRITICAL,
            location="Cooling Water Area",
        )
        work_order = WorkOrder(
            work_order_number="WO-PROP-APPROVAL-001",
            asset=asset,
            title="Inspect elevated P-101 vibration",
            description=("Inspect pump bearings, coupling alignment, and lubrication condition."),
            priority=WorkOrderPriority.HIGH,
            status=WorkOrderStatus.PENDING_APPROVAL,
            revision=1,
            proposed_by="maintenance-agent",
            idempotency_key="p101-approval-service-001",
        )
        approval = Approval(
            work_order=work_order,
            request_version=1,
            decision=ApprovalDecision.PENDING,
            approval_scope="execute_work_order",
            requested_by="maintenance-agent",
        )

        session.add(approval)
        session.commit()

        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def create_decision_input(
    *,
    decision: ApprovalDecision = ApprovalDecision.APPROVED,
    decided_by: str = "technician-001",
    decision_reason: str = "Inspection plan reviewed and approved.",
) -> WorkOrderApprovalDecisionInput:
    return WorkOrderApprovalDecisionInput(
        work_order_id=1,
        request_version=1,
        decision=decision,
        decided_by=decided_by,
        decision_reason=decision_reason,
        decision_source="human",
        approval_scope="execute_work_order",
    )


def test_human_approval_updates_work_order_and_approval(
    database_session: Session,
) -> None:
    decided_at = datetime(2026, 8, 23, 18, 0, tzinfo=UTC)

    result = decide_work_order_approval(
        database_session,
        create_decision_input(),
        decision_clock=lambda: decided_at,
    )

    work_order = database_session.get(WorkOrder, result.work_order_id)
    approval = database_session.get(Approval, result.approval_id)

    assert result.decision_applied is True
    assert result.decision == ApprovalDecision.APPROVED
    assert result.work_order_status == WorkOrderStatus.APPROVED
    assert result.decided_by == "technician-001"
    assert result.decided_at == decided_at
    assert work_order is not None
    assert approval is not None
    assert work_order.status == WorkOrderStatus.APPROVED
    assert approval.decision == ApprovalDecision.APPROVED
    assert approval.decided_by == "technician-001"
    assert approval.decision_reason == "Inspection plan reviewed and approved."


def test_human_rejection_updates_work_order_and_approval(
    database_session: Session,
) -> None:
    result = decide_work_order_approval(
        database_session,
        create_decision_input(
            decision=ApprovalDecision.REJECTED,
            decision_reason="Work scope requires further technical review.",
        ),
        decision_clock=lambda: datetime(2026, 8, 23, 18, 5, tzinfo=UTC),
    )

    assert result.decision_applied is True
    assert result.decision == ApprovalDecision.REJECTED
    assert result.work_order_status == WorkOrderStatus.REJECTED

    work_order = database_session.get(WorkOrder, result.work_order_id)
    approval = database_session.get(Approval, result.approval_id)

    assert work_order is not None
    assert approval is not None
    assert work_order.status == WorkOrderStatus.REJECTED
    assert approval.decision == ApprovalDecision.REJECTED


def test_identical_decision_retry_returns_existing_result(
    database_session: Session,
) -> None:
    decision_clock = Mock(return_value=datetime(2026, 8, 23, 18, 10, tzinfo=UTC))
    decision_input = create_decision_input()

    first_result = decide_work_order_approval(
        database_session,
        decision_input,
        decision_clock=decision_clock,
    )
    second_result = decide_work_order_approval(
        database_session,
        decision_input,
        decision_clock=decision_clock,
    )

    assert first_result.decision_applied is True
    assert second_result.decision_applied is False
    assert second_result.approval_id == first_result.approval_id
    assert second_result.decided_at == first_result.decided_at
    assert decision_clock.call_count == 1


def test_conflicting_second_decision_is_rejected(
    database_session: Session,
) -> None:
    decide_work_order_approval(
        database_session,
        create_decision_input(),
        decision_clock=lambda: datetime(2026, 8, 23, 18, 15, tzinfo=UTC),
    )

    with pytest.raises(
        WorkOrderApprovalConflictError,
        match="different final decision",
    ):
        decide_work_order_approval(
            database_session,
            create_decision_input(
                decision=ApprovalDecision.REJECTED,
                decision_reason="Reject the previously approved work scope.",
            ),
        )

    work_order = database_session.get(WorkOrder, 1)
    approval = database_session.get(Approval, 1)

    assert work_order is not None
    assert approval is not None
    assert work_order.status == WorkOrderStatus.APPROVED
    assert approval.decision == ApprovalDecision.APPROVED
