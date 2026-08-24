from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from app.agent.approval import (
    await_work_order_approval,
    prepare_approval_pause,
)
from app.agent.checkpoint import open_sqlite_checkpointer
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


def build_persistent_approval_graph(
    checkpointer,
):
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
        checkpointer=checkpointer,
    )


def create_state_with_proposal() -> AgentState:
    state = create_initial_state(
        "Investigate elevated P-101 vibration",
        "P-101",
        run_id="run-persistent-001",
        thread_id="thread-persistent-001",
    )
    state["work_order_proposal"] = WorkOrderProposalOutput(
        work_order_id=10,
        work_order_number="WO-PROP-0010",
        asset_code="P-101",
        title="Inspect elevated P-101 vibration",
        description=("Inspect pump bearings, coupling alignment, and lubrication condition."),
        priority=WorkOrderPriority.HIGH,
        status=WorkOrderStatus.PENDING_APPROVAL,
        revision=1,
        proposed_by="maintenance-agent",
        idempotency_key="p101-persistent-run-001",
        approval_id=5,
        approval_decision=ApprovalDecision.PENDING,
        request_version=1,
        approval_scope="execute_work_order",
        created_new=True,
    )

    return state


def create_resume_payload() -> WorkOrderApprovalResume:
    return WorkOrderApprovalResume(
        run_id="run-persistent-001",
        thread_id="thread-persistent-001",
        decision=WorkOrderApprovalDecisionOutput(
            work_order_id=10,
            work_order_number="WO-PROP-0010",
            approval_id=5,
            request_version=1,
            decision=ApprovalDecision.APPROVED,
            work_order_status=WorkOrderStatus.APPROVED,
            decided_by="technician-001",
            decided_at=datetime(
                2026,
                8,
                24,
                12,
                0,
                tzinfo=UTC,
            ),
            decision_reason="Inspection plan reviewed and approved.",
            approval_scope="execute_work_order",
            decision_applied=True,
        ),
    )


def test_sqlite_checkpoint_survives_close_and_reopen(
    tmp_path: Path,
) -> None:
    checkpoint_path = tmp_path / "nested" / "langgraph_checkpoints.sqlite"
    state = create_state_with_proposal()
    config = {
        "configurable": {
            "thread_id": state["thread_id"],
        }
    }

    with open_sqlite_checkpointer(checkpoint_path) as first_checkpointer:
        first_graph = build_persistent_approval_graph(first_checkpointer)
        interrupted = first_graph.invoke(
            state,
            config=config,
        )

        assert interrupted["status"] == (AgentStatus.WAITING_FOR_APPROVAL)
        assert len(interrupted["__interrupt__"]) == 1

    assert checkpoint_path.exists()

    with open_sqlite_checkpointer(checkpoint_path) as reopened_checkpointer:
        reopened_graph = build_persistent_approval_graph(reopened_checkpointer)
        resumed = reopened_graph.invoke(
            Command(
                resume=create_resume_payload().model_dump(mode="json"),
            ),
            config=config,
        )

    assert resumed["status"] == AgentStatus.COMPLETED
    assert resumed["route"] == AgentRoute.END
    assert resumed["approval_decision"] is not None
    assert resumed["approval_decision"].decision == ApprovalDecision.APPROVED
    assert resumed["visited_nodes"] == [
        "prepare_approval_pause",
        "await_work_order_approval",
    ]


def test_sqlite_checkpointer_rejects_empty_path() -> None:
    with pytest.raises(
        ValueError,
        match="must not be empty",
    ):
        with open_sqlite_checkpointer("   "):
            pass
