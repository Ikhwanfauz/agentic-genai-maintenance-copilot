from typing import Protocol

from app.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
)
from app.schemas.actions import WorkOrderProposalOutput
from app.schemas.agent_api import (
    AgentApprovalDecisionRequest,
    AgentRunResponse,
)


class OperatorActionContextError(ValueError):
    """Raised when an operator action has no valid current workflow context."""


class OperatorApiClient(Protocol):
    def get_run(
        self,
        run_id: str,
    ) -> AgentRunResponse: ...

    def submit_approval(
        self,
        run_id: str,
        request: AgentApprovalDecisionRequest,
    ) -> AgentRunResponse: ...


def refresh_agent_run(
    client: OperatorApiClient,
    run_id: str,
) -> AgentRunResponse:
    """Retrieve the latest persisted state for an active run."""

    return client.get_run(run_id)


def submit_work_order_decision(
    client: OperatorApiClient,
    run: AgentRunResponse,
    *,
    decision: ApprovalDecision,
    decided_by: str,
    decision_reason: str,
) -> AgentRunResponse:
    """Validate current approval identity and submit a human decision."""

    proposal = _validate_approval_context(run)

    request = AgentApprovalDecisionRequest(
        request_version=proposal.request_version,
        decision=decision,
        decided_by=decided_by,
        decision_reason=decision_reason,
        decision_source="human",
        approval_scope=proposal.approval_scope,
    )

    return client.submit_approval(
        run.run_id,
        request,
    )


def _validate_approval_context(
    run: AgentRunResponse,
) -> WorkOrderProposalOutput:
    if run.status != AgentRunStatus.WAITING_FOR_APPROVAL:
        raise OperatorActionContextError("The agent run is not waiting for approval.")

    if run.work_order_proposal is None:
        raise OperatorActionContextError("The agent run has no work-order proposal.")

    if run.approval_interrupt is None:
        raise OperatorActionContextError("The agent run has no approval interrupt.")

    proposal = run.work_order_proposal
    interrupt_proposal = run.approval_interrupt.proposal

    if _proposal_identity(proposal) != _proposal_identity(interrupt_proposal):
        raise OperatorActionContextError(
            "The work-order proposal does not match the current approval interrupt."
        )

    return proposal


def _proposal_identity(
    proposal: WorkOrderProposalOutput,
) -> tuple[int, str, int, int, str]:
    return (
        proposal.work_order_id,
        proposal.work_order_number,
        proposal.approval_id,
        proposal.request_version,
        proposal.approval_scope,
    )
