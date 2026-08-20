from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from app.agent.graph import build_agent_graph
from app.agent.state import (
    AgentRoute,
    AgentStatus,
    create_initial_state,
)


def test_agent_graph_invokes_model_and_appends_response() -> None:
    model = Mock()
    model.invoke.return_value = AIMessage(
        content="I will gather asset, maintenance, sensor, and document evidence."
    )
    graph = build_agent_graph(model)

    result = graph.invoke(
        create_initial_state(
            "Investigate increasing vibration on P-101",
            "P-101",
            run_id="llm-run",
        )
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert result["route"] == AgentRoute.END
    assert result["iteration_count"] == 1
    assert result["visited_nodes"] == [
        "initialize",
        "mark_ready",
        "call_model",
    ]
    assert len(result["messages"]) == 2
    assert isinstance(result["messages"][0], HumanMessage)
    assert isinstance(result["messages"][1], AIMessage)

    invocation_messages = model.invoke.call_args.args[0]
    assert isinstance(invocation_messages[0], SystemMessage)
    assert isinstance(invocation_messages[1], HumanMessage)


def test_agent_graph_stops_before_model_when_limit_is_reached() -> None:
    model = Mock()
    graph = build_agent_graph(model)
    initial_state = create_initial_state(
        "Investigate P-101",
        "P-101",
        max_iterations=1,
    )
    initial_state["iteration_count"] = 1

    result = graph.invoke(initial_state)

    assert result["status"] == AgentStatus.LIMIT_REACHED
    assert result["route"] == AgentRoute.END
    assert result["iteration_count"] == 1
    assert result["error"] is not None
    model.invoke.assert_not_called()


def test_agent_graph_rejects_empty_request_without_model_call() -> None:
    model = Mock()
    graph = build_agent_graph(model)

    result = graph.invoke(create_initial_state("   "))

    assert result["status"] == AgentStatus.REJECTED
    assert result["route"] == AgentRoute.END
    assert result["visited_nodes"] == ["initialize", "reject_request"]
    model.invoke.assert_not_called()
