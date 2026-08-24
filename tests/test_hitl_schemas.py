import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.enums import (
    ApprovalDecision,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.schemas.actions import (
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)
from app.schemas.hitl import (
    WorkOrderApprovalInterrupt,
    WorkOrderApprovalResume,
)


def create_proposal_output() -> WorkOrderProposalOutput:
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


def create_decision_output() -> WorkOrderApprovalDecisionOutput:
    return WorkOrderApprovalDecisionOutput(
        work_order_id=10,
        work_order_number="WO-PROP-0010",
        approval_id=5,
        request_version=1,
        decision=ApprovalDecision.APPROVED,
        work_order_status=WorkOrderStatus.APPROVED,
        decided_by="technician-001",
        decided_at=datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
        decision_reason="Inspection plan reviewed and approved.",
        approval_scope="execute_work_order",
        decision_applied=True,
    )


def test_approval_interrupt_contains_pending_proposal() -> None:
    payload = WorkOrderApprovalInterrupt(
        run_id=" run-001 ",
        thread_id=" thread-001 ",
        proposal=create_proposal_output(),
    )

    assert payload.interrupt_type == "work_order_approval_required"
    assert payload.run_id == "run-001"
    assert payload.thread_id == "thread-001"
    assert payload.proposal.status == WorkOrderStatus.PENDING_APPROVAL


def test_approval_interrupt_is_json_serializable() -> None:
    payload = WorkOrderApprovalInterrupt(
        run_id="run-001",
        thread_id="thread-001",
        proposal=create_proposal_output(),
    )

    serialized = payload.model_dump(mode="json")

    assert json.loads(json.dumps(serialized)) == serialized


def test_approval_resume_contains_completed_human_decision() -> None:
    payload = WorkOrderApprovalResume(
        run_id="run-001",
        thread_id="thread-001",
        decision=create_decision_output(),
    )

    assert payload.resume_type == "work_order_approval_decided"
    assert payload.decision.decision == ApprovalDecision.APPROVED
    assert payload.decision.work_order_status == WorkOrderStatus.APPROVED


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("run_id", "   "),
        ("thread_id", "   "),
    ],
)
def test_hitl_payload_rejects_blank_identifiers(
    field_name: str,
    value: str,
) -> None:
    values: dict[str, object] = {
        "run_id": "run-001",
        "thread_id": "thread-001",
        "proposal": create_proposal_output(),
    }
    values[field_name] = value

    with pytest.raises(ValidationError):
        WorkOrderApprovalInterrupt.model_validate(values)
