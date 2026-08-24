from datetime import UTC, datetime

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.agent.approval import (
    await_work_order_approval,
    prepare_approval_pause,
)
from app.agent.state import (
    AgentRoute,
    AgentState,
    AgentStatus,
    create_initial_state,
)
from app.models.enums import (
    ApprovalDecision,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.schemas.actions import (
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)
from app.schemas.hitl import WorkOrderApprovalResume


def build_approval_test_graph():
    builder = StateGraph(AgentState)

    builder.add_node(
        "prepare_approval_pause",
        prepare_approval_pause,
    )
    builder.add_node(
        "await_work_order_approval",
        await_work_order_approval,
    )

    builder.add_edge(
        START,
        "prepare_approval_pause",
    )
    builder.add_edge(
        "prepare_approval_pause",
        "await_work_order_approval",
    )
    builder.add_edge(
        "await_work_order_approval",
        END,
    )

    return builder.compile(
        checkpointer=InMemorySaver(),
    )


def create_pending_proposal() -> WorkOrderProposalOutput:
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


def create_state_with_pending_proposal() -> AgentState:
    state = create_initial_state(
        "Investigate elevated P-101 vibration",
        "P-101",
        run_id="run-001",
        thread_id="thread-001",
    )
    state["work_order_proposal"] = create_pending_proposal()

    return state


def create_resume_payload(
    decision: ApprovalDecision,
) -> WorkOrderApprovalResume:
    work_order_status = (
        WorkOrderStatus.APPROVED
        if decision == ApprovalDecision.APPROVED
        else WorkOrderStatus.REJECTED
    )
    decision_reason = (
        "Inspection plan reviewed and approved."
        if decision == ApprovalDecision.APPROVED
        else "Work scope requires further technical review."
    )

    return WorkOrderApprovalResume(
        run_id="run-001",
        thread_id="thread-001",
        decision=WorkOrderApprovalDecisionOutput(
            work_order_id=10,
            work_order_number="WO-PROP-0010",
            approval_id=5,
            request_version=1,
            decision=decision,
            work_order_status=work_order_status,
            decided_by="technician-001",
            decided_at=datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
            decision_reason=decision_reason,
            approval_scope="execute_work_order",
            decision_applied=True,
        ),
    )


def test_graph_pauses_with_pending_work_order_proposal() -> None:
    graph = build_approval_test_graph()
    state = create_state_with_pending_proposal()
    config = {
        "configurable": {
            "thread_id": state["thread_id"],
        }
    }

    result = graph.invoke(
        state,
        config=config,
    )

    assert result["status"] == AgentStatus.WAITING_FOR_APPROVAL
    assert result["route"] == AgentRoute.APPROVAL
    assert result["approval_interrupt"] is not None
    assert result["approval_decision"] is None
    assert result["visited_nodes"] == ["prepare_approval_pause"]

    interrupts = result["__interrupt__"]

    assert len(interrupts) == 1
    assert interrupts[0].value["interrupt_type"] == "work_order_approval_required"
    assert interrupts[0].value["proposal"]["work_order_id"] == 10

    snapshot = graph.get_state(config)

    assert snapshot.values["status"] == AgentStatus.WAITING_FOR_APPROVAL
    assert snapshot.next == ("await_work_order_approval",)


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
def test_graph_resumes_with_completed_human_decision(
    decision: ApprovalDecision,
    expected_status: WorkOrderStatus,
) -> None:
    graph = build_approval_test_graph()
    state = create_state_with_pending_proposal()
    config = {
        "configurable": {
            "thread_id": state["thread_id"],
        }
    }

    graph.invoke(
        state,
        config=config,
    )

    resume = create_resume_payload(decision)
    result = graph.invoke(
        Command(
            resume=resume.model_dump(mode="json"),
        ),
        config=config,
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert result["route"] == AgentRoute.END
    assert result["approval_decision"] is not None
    assert result["approval_decision"].decision == decision
    assert result["approval_decision"].work_order_status == expected_status
    assert result["visited_nodes"] == [
        "prepare_approval_pause",
        "await_work_order_approval",
    ]
    assert "__interrupt__" not in result


@pytest.mark.parametrize(
    (
        "field_name",
        "invalid_value",
        "error_match",
    ),
    [
        (
            "run_id",
            "wrong-run",
            "run does not match",
        ),
        (
            "thread_id",
            "wrong-thread",
            "thread does not match",
        ),
        (
            "work_order_id",
            999,
            "work order does not match",
        ),
        (
            "work_order_number",
            "WO-PROP-WRONG",
            "work-order number does not match",
        ),
        (
            "approval_id",
            999,
            "approval record does not match",
        ),
        (
            "request_version",
            2,
            "version does not match",
        ),
        (
            "approval_scope",
            "review_only",
            "execute_work_order",
        ),
    ],
)
def test_resume_rejects_tampered_approval_identity(
    field_name: str,
    invalid_value: object,
    error_match: str,
) -> None:
    graph = build_approval_test_graph()
    state = create_state_with_pending_proposal()
    config = {
        "configurable": {
            "thread_id": state["thread_id"],
        }
    }

    graph.invoke(
        state,
        config=config,
    )

    valid_resume = create_resume_payload(
        ApprovalDecision.APPROVED,
    )
    tampered_resume = valid_resume.model_copy(deep=True)

    if field_name in {
        "run_id",
        "thread_id",
    }:
        setattr(
            tampered_resume,
            field_name,
            invalid_value,
        )
    else:
        setattr(
            tampered_resume.decision,
            field_name,
            invalid_value,
        )

    rejected_resume = graph.invoke(
        Command(
            resume=tampered_resume.model_dump(mode="json"),
        ),
        config=config,
    )

    assert rejected_resume["status"] == (AgentStatus.WAITING_FOR_APPROVAL)
    assert rejected_resume["approval_decision"] is None
    assert len(rejected_resume["__interrupt__"]) == 1
    assert error_match in (rejected_resume["__interrupt__"][0].value["validation_error"])

    snapshot = graph.get_state(config)

    assert snapshot.values["status"] == (AgentStatus.WAITING_FOR_APPROVAL)
    assert snapshot.values["approval_decision"] is None

    recovered = graph.invoke(
        Command(
            resume=valid_resume.model_dump(mode="json"),
        ),
        config=config,
    )

    assert recovered["status"] == AgentStatus.COMPLETED
    assert recovered["approval_decision"] is not None
    assert recovered["approval_decision"].decision == ApprovalDecision.APPROVED
