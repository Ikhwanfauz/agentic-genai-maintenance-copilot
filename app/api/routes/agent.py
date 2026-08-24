from typing import Annotated, NoReturn

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy.orm import Session

from app.api.dependencies import get_agent_graph
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.agent_api import (
    AgentApprovalDecisionRequest,
    AgentInvestigationStartRequest,
    AgentRunResponse,
)
from app.services.agent_workflows import (
    AgentGraph,
    decide_agent_run_approval,
    get_agent_run,
    start_agent_investigation,
)
from app.services.exceptions import (
    AgentRunApprovalStateError,
    AgentRunNotFoundError,
    AgentWorkflowExecutionError,
    AgentWorkflowPersistenceError,
    AgentWorkflowServiceError,
    AgentWorkflowStateError,
    WorkOrderPersistenceError,
    WorkOrderServiceError,
)

router = APIRouter(
    prefix="/agent",
    tags=["agent"],
)

DatabaseSession = Annotated[
    Session,
    Depends(get_db),
]
AgentGraphDependency = Annotated[
    AgentGraph,
    Depends(get_agent_graph),
]


def _raise_http_error(
    error: Exception,
) -> NoReturn:
    if isinstance(error, AgentRunNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error

    if isinstance(
        error,
        (
            AgentWorkflowPersistenceError,
            WorkOrderPersistenceError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The workflow persistence service is unavailable.",
        ) from error

    if isinstance(
        error,
        (
            AgentRunApprovalStateError,
            AgentWorkflowStateError,
            WorkOrderServiceError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error

    if isinstance(
        error,
        (
            AgentWorkflowExecutionError,
            AgentWorkflowServiceError,
        ),
    ):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The agent workflow could not be completed.",
        ) from error

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An unexpected agent workflow error occurred.",
    ) from error


@router.post(
    "/investigations",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a maintenance investigation",
)
def start_investigation(
    request: AgentInvestigationStartRequest,
    database_session: DatabaseSession,
    graph: AgentGraphDependency,
) -> AgentRunResponse:
    settings = get_settings()
    model_name = (
        settings.azure_openai_deployment
        if settings.llm_provider == "azure_openai" and settings.azure_openai_deployment
        else settings.llm_model
    )

    try:
        return start_agent_investigation(
            database_session,
            graph,
            request,
            model_provider=settings.llm_provider,
            model_name=model_name,
        )
    except AgentWorkflowServiceError as error:
        _raise_http_error(error)


@router.get(
    "/runs/{run_id}",
    response_model=AgentRunResponse,
    summary="Get an agent run",
)
def read_agent_run(
    run_id: str,
    database_session: DatabaseSession,
    graph: AgentGraphDependency,
) -> AgentRunResponse:
    try:
        return get_agent_run(
            database_session,
            graph,
            run_id,
        )
    except AgentWorkflowServiceError as error:
        _raise_http_error(error)


@router.post(
    "/runs/{run_id}/approval",
    response_model=AgentRunResponse,
    summary="Apply a human approval decision",
)
def decide_run_approval(
    run_id: str,
    request: AgentApprovalDecisionRequest,
    database_session: DatabaseSession,
    graph: AgentGraphDependency,
) -> AgentRunResponse:
    try:
        return decide_agent_run_approval(
            database_session,
            graph,
            run_id,
            request,
        )
    except (
        AgentWorkflowServiceError,
        WorkOrderServiceError,
    ) as error:
        _raise_http_error(error)
