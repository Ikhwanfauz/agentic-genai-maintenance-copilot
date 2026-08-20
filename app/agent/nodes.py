from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage

from app.agent.prompts import MAINTENANCE_COPILOT_SYSTEM_PROMPT
from app.agent.state import AgentRoute, AgentState, AgentStatus


def create_call_model_node(
    model: BaseChatModel,
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

        return {
            "messages": [response],
            "iteration_count": state["iteration_count"] + 1,
            "status": AgentStatus.COMPLETED,
            "route": AgentRoute.END,
            "visited_nodes": ["call_model"],
            "error": None,
        }

    return call_model
