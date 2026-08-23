from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.approval import Approval
from app.models.enums import (
    ApprovalDecision,
    WorkOrderStatus,
)
from app.models.work_order import WorkOrder
from app.schemas.actions import (
    WorkOrderApprovalDecisionInput,
    WorkOrderApprovalDecisionOutput,
)
from app.services.exceptions import (
    WorkOrderApprovalConflictError,
    WorkOrderApprovalNotFoundError,
    WorkOrderApprovalStateError,
    WorkOrderApprovalVersionConflictError,
    WorkOrderNotFoundError,
    WorkOrderPersistenceError,
    WorkOrderServiceError,
)

ApprovalDecisionClock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _work_order_status_for(
    decision: ApprovalDecision,
) -> WorkOrderStatus:
    if decision == ApprovalDecision.APPROVED:
        return WorkOrderStatus.APPROVED

    return WorkOrderStatus.REJECTED


def _build_decision_output(
    work_order: WorkOrder,
    approval: Approval,
    *,
    decision_applied: bool,
) -> WorkOrderApprovalDecisionOutput:
    if (
        approval.decided_by is None
        or approval.decided_at is None
        or approval.decision_reason is None
    ):
        raise WorkOrderApprovalStateError("A completed approval decision requires audit metadata.")

    return WorkOrderApprovalDecisionOutput(
        work_order_id=work_order.id,
        work_order_number=work_order.work_order_number,
        approval_id=approval.id,
        request_version=approval.request_version,
        decision=approval.decision,
        work_order_status=work_order.status,
        decided_by=approval.decided_by,
        decided_at=_normalize_utc_timestamp(approval.decided_at),
        decision_reason=approval.decision_reason,
        approval_scope=approval.approval_scope,
        decision_applied=decision_applied,
    )


def _return_existing_decision(
    database_session: Session,
    work_order: WorkOrder,
    approval: Approval,
    decision_input: WorkOrderApprovalDecisionInput,
) -> WorkOrderApprovalDecisionOutput:
    expected_status = _work_order_status_for(decision_input.decision)

    if (
        approval.decision != decision_input.decision
        or work_order.status != expected_status
        or approval.decided_by != decision_input.decided_by
        or approval.decision_reason != decision_input.decision_reason
        or approval.approval_scope != decision_input.approval_scope
    ):
        raise WorkOrderApprovalConflictError(
            "The approval request already has a different final decision."
        )

    output = _build_decision_output(
        work_order,
        approval,
        decision_applied=False,
    )
    database_session.rollback()

    return output


def decide_work_order_approval(
    database_session: Session,
    decision_input: WorkOrderApprovalDecisionInput,
    *,
    decision_clock: ApprovalDecisionClock = utc_now,
) -> WorkOrderApprovalDecisionOutput:
    try:
        work_order = database_session.get(
            WorkOrder,
            decision_input.work_order_id,
        )

        if work_order is None:
            raise WorkOrderNotFoundError(decision_input.work_order_id)

        if decision_input.request_version != work_order.revision:
            raise WorkOrderApprovalVersionConflictError(
                decision_input.request_version,
                work_order.revision,
            )

        approval = database_session.scalar(
            select(Approval).where(
                Approval.work_order_id == work_order.id,
                Approval.request_version == decision_input.request_version,
            )
        )

        if approval is None:
            raise WorkOrderApprovalNotFoundError(
                work_order.id,
                decision_input.request_version,
            )

        if (
            approval.decision != ApprovalDecision.PENDING
            or work_order.status != WorkOrderStatus.PENDING_APPROVAL
        ):
            return _return_existing_decision(
                database_session,
                work_order,
                approval,
                decision_input,
            )

        if approval.approval_scope != decision_input.approval_scope:
            raise WorkOrderApprovalStateError(
                "The requested approval scope does not match the pending request."
            )

        decided_at = decision_clock()

        if decided_at.tzinfo is None or decided_at.utcoffset() is None:
            raise WorkOrderApprovalStateError(
                "Approval decision timestamps must include timezone information."
            )

        approval.decision = decision_input.decision
        approval.decided_by = decision_input.decided_by
        approval.decided_at = decided_at
        approval.decision_reason = decision_input.decision_reason
        work_order.status = _work_order_status_for(decision_input.decision)

        database_session.commit()
        database_session.refresh(work_order)
        database_session.refresh(approval)

        return _build_decision_output(
            work_order,
            approval,
            decision_applied=True,
        )
    except WorkOrderServiceError:
        database_session.rollback()
        raise
    except SQLAlchemyError as error:
        database_session.rollback()
        raise WorkOrderPersistenceError("The work-order approval transaction failed.") from error
