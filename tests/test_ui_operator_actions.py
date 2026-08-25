from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
    WorkOrderPriority,
)
from app.schemas.actions import WorkOrderProposalOutput
from app.schemas.agent_api import (
    AgentApprovalDecisionRequest,
    AgentRunResponse,
)
from app.schemas.hitl import WorkOrderApprovalInterrupt
from app.ui.operator_actions import (
    OperatorActionContextError,
    refresh_agent_run,
    submit_work_order_decision,
)


def work_order_proposal(
    *,
    request_version: int = 1,
) -> WorkOrderProposalOutput:
    return WorkOrderProposalOutput(
        asset_code="P-101",
        work_order_id=101,
        work_order_number="WO-PROP-UI-001",
        title="Inspect P-101 rotating assembly",
        description=(
            "Inspect the pump bearings, alignment, and coupling "
            "before returning the asset to normal service."
        ),
        priority=WorkOrderPriority.HIGH,
        revision=1,
        proposed_by="maintenance_copilot",
        idempotency_key="run-ui-approval:P-101",
        approval_id=501,
        request_version=request_version,
        created_new=True,
    )


def waiting_run(
    *,
    proposal: WorkOrderProposalOutput | None = None,
    interrupt_proposal: WorkOrderProposalOutput | None = None,
) -> AgentRunResponse:
    active_proposal = proposal or work_order_proposal()
    active_interrupt_proposal = interrupt_proposal or active_proposal

    return AgentRunResponse(
        run_id="run-ui-approval",
        thread_id="thread-ui-approval",
        status=AgentRunStatus.WAITING_FOR_APPROVAL,
        started_at=datetime(
            2026,
            8,
            26,
            12,
            0,
            tzinfo=UTC,
        ),
        work_order_proposal=active_proposal,
        approval_interrupt=WorkOrderApprovalInterrupt(
            run_id="run-ui-approval",
            thread_id="thread-ui-approval",
            proposal=active_interrupt_proposal,
        ),
    )


def completed_run() -> AgentRunResponse:
    return AgentRunResponse(
        run_id="run-ui-approval",
        thread_id="thread-ui-approval",
        status=AgentRunStatus.COMPLETED,
        started_at=datetime(
            2026,
            8,
            26,
            12,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            8,
            26,
            12,
            5,
            tzinfo=UTC,
        ),
        final_response="Human decision applied.",
    )


class FakeOperatorApiClient:
    def __init__(self) -> None:
        self.run_response = completed_run()
        self.received_run_id: str | None = None
        self.received_request: AgentApprovalDecisionRequest | None = None

    def get_run(
        self,
        run_id: str,
    ) -> AgentRunResponse:
        self.received_run_id = run_id
        return self.run_response

    def submit_approval(
        self,
        run_id: str,
        request: AgentApprovalDecisionRequest,
    ) -> AgentRunResponse:
        self.received_run_id = run_id
        self.received_request = request
        return self.run_response


def test_refresh_agent_run_uses_active_run_identity() -> None:
    client = FakeOperatorApiClient()

    response = refresh_agent_run(
        client,
        "run-ui-approval",
    )

    assert response.status == AgentRunStatus.COMPLETED
    assert client.received_run_id == "run-ui-approval"


@pytest.mark.parametrize(
    "decision",
    [
        ApprovalDecision.APPROVED,
        ApprovalDecision.REJECTED,
    ],
)
def test_submit_decision_uses_current_approval_context(
    decision: ApprovalDecision,
) -> None:
    client = FakeOperatorApiClient()

    response = submit_work_order_decision(
        client,
        waiting_run(),
        decision=decision,
        decided_by="  Shift Supervisor  ",
        decision_reason=("  Evidence and proposed inspection scope reviewed.  "),
    )

    assert response.status == AgentRunStatus.COMPLETED
    assert client.received_run_id == "run-ui-approval"
    assert client.received_request is not None
    assert client.received_request.request_version == 1
    assert client.received_request.decision == decision
    assert client.received_request.decided_by == ("Shift Supervisor")
    assert client.received_request.decision_reason == (
        "Evidence and proposed inspection scope reviewed."
    )
    assert client.received_request.decision_source == "human"
    assert client.received_request.approval_scope == ("execute_work_order")


def test_decision_rejects_run_not_waiting_for_approval() -> None:
    client = FakeOperatorApiClient()

    with pytest.raises(
        OperatorActionContextError,
        match="not waiting for approval",
    ):
        submit_work_order_decision(
            client,
            completed_run(),
            decision=ApprovalDecision.APPROVED,
            decided_by="Shift Supervisor",
            decision_reason="The proposed action was reviewed.",
        )

    assert client.received_request is None


def test_decision_rejects_mismatched_interrupt_identity() -> None:
    client = FakeOperatorApiClient()
    proposal = work_order_proposal(
        request_version=1,
    )
    stale_interrupt_proposal = work_order_proposal(
        request_version=2,
    )

    run = waiting_run(
        proposal=proposal,
        interrupt_proposal=stale_interrupt_proposal,
    )

    with pytest.raises(
        OperatorActionContextError,
        match="does not match",
    ):
        submit_work_order_decision(
            client,
            run,
            decision=ApprovalDecision.REJECTED,
            decided_by="Shift Supervisor",
            decision_reason="The approval identity is stale.",
        )

    assert client.received_request is None


@pytest.mark.parametrize(
    ("decided_by", "decision_reason"),
    [
        (
            "",
            "The proposed action was reviewed.",
        ),
        (
            "Shift Supervisor",
            "",
        ),
        (
            "Shift Supervisor",
            "No.",
        ),
    ],
)
def test_decision_rejects_invalid_human_input(
    decided_by: str,
    decision_reason: str,
) -> None:
    client = FakeOperatorApiClient()

    with pytest.raises(ValidationError):
        submit_work_order_decision(
            client,
            waiting_run(),
            decision=ApprovalDecision.APPROVED,
            decided_by=decided_by,
            decision_reason=decision_reason,
        )

    assert client.received_request is None
