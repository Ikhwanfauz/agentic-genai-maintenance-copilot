from collections.abc import Callable

from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable

from app.agent.prompts import MAINTENANCE_COPILOT_SYSTEM_PROMPT
from app.agent.state import AgentRoute, AgentState, AgentStatus


def create_call_model_node(
    model: Runnable,
    *,
    require_structured_diagnosis: bool = False,
) -> Callable[[AgentState], dict[str, object]]:
    def call_model(state: AgentState) -> dict[str, object]:
        if state["iteration_count"] >= state["max_iterations"]:
            return {
                "status": AgentStatus.LIMIT_REACHED,
                "route": AgentRoute.END,
                "visited_nodes": ["call_model"],
                "error": "The agent reached its maximum iteration limit.",
            }

        response = model.invoke(
            [
                SystemMessage(content=MAINTENANCE_COPILOT_SYSTEM_PROMPT),
                *state["messages"],
            ]
        )
        next_iteration_count = state["iteration_count"] + 1
        tool_calls = getattr(response, "tool_calls", [])

        if len(tool_calls) > 1:
            return {
                "messages": [response],
                "iteration_count": next_iteration_count,
                "status": AgentStatus.FAILED,
                "route": AgentRoute.END,
                "visited_nodes": ["call_model"],
                "error": "The model requested more than one tool call in one iteration.",
            }

        if tool_calls:
            if next_iteration_count >= state["max_iterations"]:
                return {
                    "messages": [response],
                    "iteration_count": next_iteration_count,
                    "status": AgentStatus.LIMIT_REACHED,
                    "route": AgentRoute.END,
                    "visited_nodes": ["call_model"],
                    "error": ("The model requested a tool call at the maximum iteration boundary."),
                }

            return {
                "messages": [response],
                "iteration_count": next_iteration_count,
                "status": AgentStatus.AWAITING_TOOL,
                "route": AgentRoute.TOOLS,
                "visited_nodes": ["call_model"],
                "error": None,
            }

        return {
            "messages": [response],
            "iteration_count": next_iteration_count,
            "status": (
                AgentStatus.RUNNING if require_structured_diagnosis else AgentStatus.COMPLETED
            ),
            "route": (AgentRoute.SYNTHESIZE if require_structured_diagnosis else AgentRoute.END),
            "visited_nodes": ["call_model"],
            "error": None,
        }

    return call_model
