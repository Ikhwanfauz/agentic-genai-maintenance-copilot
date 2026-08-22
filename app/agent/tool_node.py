from collections.abc import Callable, Sequence

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

from app.agent.evidence import collect_tool_evidence
from app.agent.state import AgentState, AgentStatus


def create_execute_tools_node(
    tools: Sequence[BaseTool],
) -> Callable[[AgentState], dict[str, object]]:
    tool_node = ToolNode(
        list(tools),
        handle_tool_errors=True,
    )

    def execute_tools(state: AgentState) -> dict[str, object]:
        result = tool_node.invoke(state)
        evidence_ledger = [
            evidence
            for message in result["messages"]
            if isinstance(message, ToolMessage)
            for evidence in collect_tool_evidence(message)
        ]

        return {
            "messages": result["messages"],
            "evidence_ledger": evidence_ledger,
            "status": AgentStatus.RUNNING,
            "visited_nodes": ["execute_tools"],
        }

    return execute_tools
