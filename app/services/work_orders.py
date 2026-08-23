from collections.abc import Callable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.models.approval import Approval
from app.models.asset import Asset
from app.models.enums import (
    ApprovalDecision,
    WorkOrderStatus,
)
from app.models.work_order import WorkOrder
from app.schemas.actions import (
    WorkOrderProposalInput,
    WorkOrderProposalOutput,
)
from app.services.exceptions import (
    WorkOrderAssetNotFoundError,
    WorkOrderIdempotencyConflictError,
    WorkOrderPersistenceError,
    WorkOrderProposalStateError,
    WorkOrderServiceError,
)

WorkOrderNumberFactory = Callable[[], str]


def generate_work_order_number() -> str:
    return f"WO-PROP-{uuid4().hex[:12].upper()}"


def _proposal_matches_existing(
    work_order: WorkOrder,
    proposal: WorkOrderProposalInput,
) -> bool:
    return (
        work_order.asset.asset_code == proposal.asset_code
        and work_order.title == proposal.title
        and work_order.description == proposal.description
        and work_order.priority == proposal.priority
        and work_order.proposed_by == proposal.proposed_by
        and work_order.idempotency_key == proposal.idempotency_key
    )


def _get_current_approval(
    database_session: Session,
    work_order: WorkOrder,
) -> Approval:
    approval = database_session.scalar(
        select(Approval).where(
            Approval.work_order_id == work_order.id,
            Approval.request_version == work_order.revision,
        )
    )

    if approval is None:
        raise WorkOrderProposalStateError(
            "The existing work-order proposal has no matching approval request."
        )

    return approval


def _build_proposal_output(
    work_order: WorkOrder,
    approval: Approval,
    *,
    created_new: bool,
) -> WorkOrderProposalOutput:
    return WorkOrderProposalOutput(
        work_order_id=work_order.id,
        work_order_number=work_order.work_order_number,
        asset_code=work_order.asset.asset_code,
        title=work_order.title,
        description=work_order.description,
        priority=work_order.priority,
        status=work_order.status,
        revision=work_order.revision,
        proposed_by=work_order.proposed_by,
        idempotency_key=work_order.idempotency_key,
        approval_id=approval.id,
        approval_decision=approval.decision,
        request_version=approval.request_version,
        approval_scope=approval.approval_scope,
        created_new=created_new,
    )


def _return_existing_proposal(
    database_session: Session,
    work_order: WorkOrder,
    proposal: WorkOrderProposalInput,
) -> WorkOrderProposalOutput:
    if not _proposal_matches_existing(
        work_order,
        proposal,
    ):
        raise WorkOrderIdempotencyConflictError(proposal.idempotency_key)

    approval = _get_current_approval(
        database_session,
        work_order,
    )

    if work_order.status != WorkOrderStatus.PENDING_APPROVAL:
        raise WorkOrderProposalStateError("The existing work order is no longer pending approval.")

    if approval.decision != ApprovalDecision.PENDING:
        raise WorkOrderProposalStateError("The existing approval request is no longer pending.")

    if approval.approval_scope != proposal.approval_scope:
        raise WorkOrderIdempotencyConflictError(proposal.idempotency_key)

    return _build_proposal_output(
        work_order,
        approval,
        created_new=False,
    )


def propose_work_order(
    database_session: Session,
    proposal: WorkOrderProposalInput,
    *,
    work_order_number_factory: WorkOrderNumberFactory = (generate_work_order_number),
) -> WorkOrderProposalOutput:
    try:
        existing_work_order = database_session.scalar(
            select(WorkOrder)
            .where(WorkOrder.idempotency_key == proposal.idempotency_key)
            .options(
                selectinload(WorkOrder.asset),
            )
        )

        if existing_work_order is not None:
            output = _return_existing_proposal(
                database_session,
                existing_work_order,
                proposal,
            )
            database_session.rollback()
            return output

        asset = database_session.scalar(
            select(Asset).where(Asset.asset_code == proposal.asset_code)
        )

        if asset is None:
            raise WorkOrderAssetNotFoundError(proposal.asset_code)

        work_order_number = work_order_number_factory().strip()

        if not 1 <= len(work_order_number) <= 30:
            raise WorkOrderProposalStateError(
                "Generated work-order number must contain between 1 and 30 characters."
            )

        work_order = WorkOrder(
            work_order_number=work_order_number,
            asset=asset,
            title=proposal.title,
            description=proposal.description,
            priority=proposal.priority,
            status=WorkOrderStatus.PENDING_APPROVAL,
            revision=1,
            proposed_by=proposal.proposed_by,
            idempotency_key=proposal.idempotency_key,
        )
        approval = Approval(
            work_order=work_order,
            request_version=work_order.revision,
            decision=ApprovalDecision.PENDING,
            approval_scope=proposal.approval_scope,
            requested_by=proposal.proposed_by,
        )

        database_session.add(approval)
        database_session.commit()
        database_session.refresh(work_order)
        database_session.refresh(approval)

        return _build_proposal_output(
            work_order,
            approval,
            created_new=True,
        )
    except WorkOrderServiceError:
        database_session.rollback()
        raise
    except SQLAlchemyError as error:
        database_session.rollback()
        raise WorkOrderPersistenceError("The work-order proposal transaction failed.") from error
