import logging
from typing import cast

from fastapi import HTTPException, Request, status

from app.services.agent_workflows import AgentGraph

logger = logging.getLogger(__name__)


def _runtime_unavailable() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="The agent workflow runtime is not available.",
    )


def get_agent_graph(
    request: Request,
) -> AgentGraph:
    application_state = request.app.state
    graph = getattr(
        application_state,
        "agent_graph",
        None,
    )

    if graph is not None:
        return cast(AgentGraph, graph)

    runtime_factory = getattr(
        application_state,
        "agent_runtime_factory",
        None,
    )
    runtime_lock = getattr(
        application_state,
        "agent_runtime_lock",
        None,
    )

    if runtime_factory is None or runtime_lock is None:
        raise _runtime_unavailable()

    with runtime_lock:
        graph = getattr(
            application_state,
            "agent_graph",
            None,
        )

        if graph is not None:
            return cast(AgentGraph, graph)

        try:
            runtime_context = runtime_factory()
            runtime = runtime_context.__enter__()
        except Exception as error:
            logger.exception("Agent workflow runtime initialization failed")
            raise _runtime_unavailable() from error

        application_state.agent_runtime_context = runtime_context
        application_state.agent_graph = runtime.graph

        return cast(
            AgentGraph,
            runtime.graph,
        )
