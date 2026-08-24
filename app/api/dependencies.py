from typing import cast

from fastapi import HTTPException, Request, status

from app.services.agent_workflows import AgentGraph


def get_agent_graph(
    request: Request,
) -> AgentGraph:
    graph = getattr(
        request.app.state,
        "agent_graph",
        None,
    )

    if graph is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The agent workflow runtime is not available.",
        )

    return cast(AgentGraph, graph)
