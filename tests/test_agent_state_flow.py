import pytest
from langchain_core.messages import HumanMessage

from app.agent.graph import build_state_flow
from app.agent.state import (
    AgentRoute,
    AgentStatus,
    create_initial_state,
)


def test_create_initial_state_normalizes_request() -> None:
    state = create_initial_state(
        "  Investigate increasing vibration  ",
        " p-101 ",
        run_id="test-run",
    )

    assert state["run_id"] == "test-run"
    assert state["user_query"] == "Investigate increasing vibration"
    assert state["asset_code"] == "P-101"
    assert state["iteration_count"] == 0
    assert state["max_iterations"] == 6
    assert state["status"] == AgentStatus.PENDING
    assert state["evidence_ledger"] == []
    assert state["evidence_coverage"] is None
    assert isinstance(state["messages"][0], HumanMessage)


def test_state_flow_routes_valid_request_to_investigation() -> None:
    graph = build_state_flow()
    initial_state = create_initial_state(
        "Investigate P-101 vibration",
        "P-101",
        run_id="valid-run",
    )

    result = graph.invoke(initial_state)

    assert result["status"] == AgentStatus.READY
    assert result["route"] == AgentRoute.INVESTIGATE
    assert result["visited_nodes"] == ["initialize", "mark_ready"]
    assert result["error"] is None
    assert result["evidence_coverage"].decision == "incomplete"
    assert len(result["evidence_coverage"].missing_sources) == 4
    assert len(result["messages"]) == 1


def test_state_flow_rejects_empty_request() -> None:
    graph = build_state_flow()
    initial_state = create_initial_state(
        "   ",
        run_id="empty-run",
    )

    result = graph.invoke(initial_state)

    assert result["status"] == AgentStatus.REJECTED
    assert result["route"] == AgentRoute.END
    assert result["visited_nodes"] == ["initialize", "reject_request"]
    assert result["error"] is not None


@pytest.mark.parametrize("max_iterations", [0, 11])
def test_initial_state_enforces_iteration_boundary(
    max_iterations: int,
) -> None:
    with pytest.raises(ValueError, match="between 1 and 10"):
        create_initial_state(
            "Investigate P-101",
            max_iterations=max_iterations,
        )
