from datetime import date
from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import StructuredTool

from app.agent.graph import build_agent_graph
from app.agent.state import AgentRoute, AgentStatus, create_initial_state
from app.schemas.asset import AssetDetailsInput


def create_asset_tool(function: Mock) -> StructuredTool:
    def run_get_asset_details(
        asset_code: str,
    ) -> dict[str, object]:
        result = function(asset_code=asset_code)
        return dict(result)

    return StructuredTool.from_function(
        func=run_get_asset_details,
        name="get_asset_details",
        description="Retrieve details for one maintenance asset.",
        args_schema=AssetDetailsInput,
    )


def create_asset_tool_call(
    call_id: str = "asset-call-1",
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_asset_details",
                "args": {"asset_code": "P-101"},
                "id": call_id,
                "type": "tool_call",
            }
        ],
    )


def test_agent_executes_tool_and_returns_to_model() -> None:
    model = Mock()
    model.invoke.side_effect = [
        create_asset_tool_call(),
        AIMessage(
            content=(
                "P-101 is the critical Main Cooling Water Pump. "
                "Additional maintenance and sensor evidence is required."
            )
        ),
    ]
    tool_function = Mock(
        return_value={
            "id": 1,
            "asset_code": "P-101",
            "name": "Main Cooling Water Pump",
            "asset_type": "pump",
            "status": "operational",
            "criticality": "critical",
            "location": "Utilities Area",
            "manufacturer": "FlowServe Simulation",
            "model_number": "CS-200",
            "installation_date": date(2021, 6, 15).isoformat(),
            "description": "Synthetic main cooling-water pump.",
            "parent_asset_code": None,
            "child_asset_codes": ["M-101"],
        }
    )
    asset_tool = create_asset_tool(tool_function)
    graph = build_agent_graph(model, [asset_tool])

    result = graph.invoke(
        create_initial_state(
            "Investigate increasing vibration on P-101",
            "P-101",
            max_iterations=3,
            run_id="tool-loop-run",
        )
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert result["route"] == AgentRoute.END
    assert result["iteration_count"] == 2
    assert result["visited_nodes"] == [
        "initialize",
        "mark_ready",
        "call_model",
        "execute_tools",
        "call_model",
    ]
    assert model.invoke.call_count == 2
    tool_function.assert_called_once_with(asset_code="P-101")

    assert isinstance(result["messages"][0], HumanMessage)
    assert isinstance(result["messages"][1], AIMessage)
    assert isinstance(result["messages"][2], ToolMessage)
    assert isinstance(result["messages"][3], AIMessage)
    assert "P-101" in result["messages"][2].content
    assert len(result["evidence_ledger"]) == 1
    assert result["evidence_ledger"][0].citation == "asset:P-101"
    assert result["evidence_coverage"].decision == "incomplete"
    assert len(result["evidence_coverage"].missing_sources) == 3


def test_agent_does_not_execute_tool_at_iteration_boundary() -> None:
    model = Mock()
    model.invoke.return_value = create_asset_tool_call()
    tool_function = Mock(return_value={"asset_code": "P-101"})
    graph = build_agent_graph(
        model,
        [create_asset_tool(tool_function)],
    )

    result = graph.invoke(
        create_initial_state(
            "Investigate P-101",
            "P-101",
            max_iterations=1,
        )
    )

    assert result["status"] == AgentStatus.LIMIT_REACHED
    assert result["route"] == AgentRoute.END
    assert result["iteration_count"] == 1
    assert result["error"] is not None
    tool_function.assert_not_called()
    assert not any(isinstance(message, ToolMessage) for message in result["messages"])


def test_agent_rejects_multiple_tool_calls_in_one_iteration() -> None:
    model = Mock()
    model.invoke.return_value = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_asset_details",
                "args": {"asset_code": "P-101"},
                "id": "asset-call-1",
                "type": "tool_call",
            },
            {
                "name": "get_asset_details",
                "args": {"asset_code": "P-102"},
                "id": "asset-call-2",
                "type": "tool_call",
            },
        ],
    )
    tool_function = Mock(return_value={"asset_code": "P-101"})
    graph = build_agent_graph(
        model,
        [create_asset_tool(tool_function)],
    )

    result = graph.invoke(
        create_initial_state(
            "Compare P-101 and P-102",
            max_iterations=3,
        )
    )

    assert result["status"] == AgentStatus.FAILED
    assert result["route"] == AgentRoute.END
    assert result["iteration_count"] == 1
    assert "more than one tool call" in result["error"]
    tool_function.assert_not_called()
