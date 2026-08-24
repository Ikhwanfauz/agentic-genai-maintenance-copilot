from langgraph.types import interrupt

from app.agent.state import (
    AgentRoute,
    AgentState,
    AgentStatus,
)
from app.schemas.hitl import (
    WorkOrderApprovalInterrupt,
    WorkOrderApprovalResume,
)


def prepare_approval_pause(
    state: AgentState,
) -> dict[str, object]:
    proposal = state["work_order_proposal"]

    if proposal is None:
        raise ValueError("A pending work-order proposal is required before approval pause.")

    approval_interrupt = WorkOrderApprovalInterrupt(
        run_id=state["run_id"],
        thread_id=state["thread_id"],
        proposal=proposal,
    )

    return {
        "status": AgentStatus.WAITING_FOR_APPROVAL,
        "route": AgentRoute.APPROVAL,
        "approval_interrupt": approval_interrupt,
        "visited_nodes": ["prepare_approval_pause"],
        "error": None,
    }


def _validate_resume_matches_interrupt(
    state: AgentState,
    resume: WorkOrderApprovalResume,
) -> None:
    approval_interrupt = state["approval_interrupt"]
    proposal = state["work_order_proposal"]

    if approval_interrupt is None or proposal is None:
        raise ValueError("Approval resume requires an existing approval interrupt.")

    if resume.run_id != state["run_id"]:
        raise ValueError("Approval resume run does not match the interrupted run.")

    if resume.thread_id != state["thread_id"]:
        raise ValueError("Approval resume thread does not match the interrupted thread.")

    decision = resume.decision

    if decision.work_order_id != proposal.work_order_id:
        raise ValueError("Approval resume work order does not match the pending proposal.")

    if decision.work_order_number != proposal.work_order_number:
        raise ValueError("Approval resume work-order number does not match the pending proposal.")

    if decision.approval_id != proposal.approval_id:
        raise ValueError("Approval resume approval record does not match the pending proposal.")

    if decision.request_version != proposal.request_version:
        raise ValueError("Approval resume version does not match the pending proposal.")

    if decision.approval_scope != proposal.approval_scope:
        raise ValueError("Approval resume scope does not match the pending proposal.")


def await_work_order_approval(
    state: AgentState,
) -> dict[str, object]:
    approval_interrupt = state["approval_interrupt"]

    if approval_interrupt is None:
        raise ValueError("Approval interrupt payload must be prepared before waiting.")

    resume_value = interrupt(approval_interrupt.model_dump(mode="json"))
    resume = WorkOrderApprovalResume.model_validate(resume_value)

    _validate_resume_matches_interrupt(
        state,
        resume,
    )

    return {
        "status": AgentStatus.COMPLETED,
        "route": AgentRoute.END,
        "approval_decision": resume.decision,
        "visited_nodes": ["await_work_order_approval"],
        "error": None,
    }
