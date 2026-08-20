from typing import Literal

from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph

from app.agent.nodes import create_call_model_node
from app.agent.state import AgentRoute, AgentState, AgentStatus


def initialize_request(_state: AgentState) -> dict[str, object]:
    return {
        "status": AgentStatus.RUNNING,
        "visited_nodes": ["initialize"],
    }


def route_request(
    state: AgentState,
) -> Literal["mark_ready", "reject_request"]:
    if not state["user_query"]:
        return "reject_request"

    return "mark_ready"


def mark_ready(_state: AgentState) -> dict[str, object]:
    return {
        "status": AgentStatus.READY,
        "route": AgentRoute.INVESTIGATE,
        "visited_nodes": ["mark_ready"],
        "error": None,
    }


def reject_request(_state: AgentState) -> dict[str, object]:
    return {
        "status": AgentStatus.REJECTED,
        "route": AgentRoute.END,
        "visited_nodes": ["reject_request"],
        "error": "A non-empty maintenance investigation request is required.",
    }


def build_state_flow():
    builder = StateGraph(AgentState)

    builder.add_node("initialize", initialize_request)
    builder.add_node("mark_ready", mark_ready)
    builder.add_node("reject_request", reject_request)

    builder.add_edge(START, "initialize")
    builder.add_conditional_edges("initialize", route_request)
    builder.add_edge("mark_ready", END)
    builder.add_edge("reject_request", END)

    return builder.compile()


def build_agent_graph(model: Runnable):
    builder = StateGraph(AgentState)

    builder.add_node("initialize", initialize_request)
    builder.add_node("mark_ready", mark_ready)
    builder.add_node("reject_request", reject_request)
    builder.add_node("call_model", create_call_model_node(model))

    builder.add_edge(START, "initialize")
    builder.add_conditional_edges("initialize", route_request)
    builder.add_edge("mark_ready", "call_model")
    builder.add_edge("call_model", END)
    builder.add_edge("reject_request", END)

    return builder.compile()
