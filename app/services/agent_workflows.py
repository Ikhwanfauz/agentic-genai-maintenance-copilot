from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.state import (
    AgentStatus,
    create_initial_state,
)
from app.models.agent_log import AgentRun
from app.models.enums import AgentRunStatus
from app.schemas.actions import (
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)
from app.schemas.agent_api import (
    AgentInvestigationStartRequest,
    AgentRunResponse,
)
from app.schemas.diagnosis import (
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.hitl import WorkOrderApprovalInterrupt
from app.services.exceptions import (
    AgentWorkflowExecutionError,
    AgentWorkflowPersistenceError,
)

WorkflowClock = Callable[[], datetime]
RunIdFactory = Callable[[], str]


class AgentGraph(Protocol):
    def invoke(
        self,
        input: object,
        *,
        config: dict[str, object],
    ) -> Mapping[str, object]: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_run_id() -> str:
    return str(uuid4())


def _normalize_utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Agent workflow timestamps must include timezone information.")

    return value.astimezone(UTC)


def _duration_ms(
    started_at: datetime,
    completed_at: datetime,
) -> int:
    elapsed_seconds = max(
        0.0,
        (completed_at - started_at).total_seconds(),
    )

    return int(elapsed_seconds * 1000)


def _validate_optional_model(
    model_type: type,
    value: object,
) -> object | None:
    if value is None:
        return None

    return model_type.model_validate(value)


def _resolve_public_status(
    agent_status: AgentStatus,
    diagnosis: MaintenanceDiagnosis | None,
) -> AgentRunStatus:
    if agent_status == AgentStatus.WAITING_FOR_APPROVAL:
        return AgentRunStatus.WAITING_FOR_APPROVAL

    if agent_status == AgentStatus.COMPLETED:
        if (
            diagnosis is not None
            and diagnosis.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
        ):
            return AgentRunStatus.ABSTAINED

        return AgentRunStatus.COMPLETED

    if agent_status in {
        AgentStatus.FAILED,
        AgentStatus.LIMIT_REACHED,
        AgentStatus.REJECTED,
    }:
        return AgentRunStatus.FAILED

    raise ValueError(f"Agent graph returned non-terminal status '{agent_status.value}'.")


def _validate_graph_result(
    result: Mapping[str, object],
) -> tuple[
    AgentRunStatus,
    MaintenanceDiagnosis | None,
    WorkOrderProposalOutput | None,
    WorkOrderApprovalInterrupt | None,
    WorkOrderApprovalDecisionOutput | None,
    str | None,
]:
    agent_status = AgentStatus(result["status"])

    diagnosis = _validate_optional_model(
        MaintenanceDiagnosis,
        result.get("diagnosis"),
    )
    proposal = _validate_optional_model(
        WorkOrderProposalOutput,
        result.get("work_order_proposal"),
    )
    approval_interrupt = _validate_optional_model(
        WorkOrderApprovalInterrupt,
        result.get("approval_interrupt"),
    )
    approval_decision = _validate_optional_model(
        WorkOrderApprovalDecisionOutput,
        result.get("approval_decision"),
    )

    error_value = result.get("error")
    error_message = str(error_value) if error_value is not None else None

    public_status = _resolve_public_status(
        agent_status,
        diagnosis,
    )

    return (
        public_status,
        diagnosis,
        proposal,
        approval_interrupt,
        approval_decision,
        error_message,
    )


def _commit_run(
    database_session: Session,
    run: AgentRun,
) -> None:
    try:
        database_session.add(run)
        database_session.commit()
    except SQLAlchemyError as error:
        database_session.rollback()
        raise AgentWorkflowPersistenceError("The agent-run database transaction failed.") from error


def _record_execution_failure(
    database_session: Session,
    run: AgentRun,
    error: Exception,
    *,
    completed_at: datetime,
) -> None:
    run.status = AgentRunStatus.FAILED
    run.completed_at = completed_at
    run.duration_ms = _duration_ms(
        run.started_at,
        completed_at,
    )
    run.error_type = type(error).__name__
    run.error_message = str(error)[:4000]

    _commit_run(
        database_session,
        run,
    )


def start_agent_investigation(
    database_session: Session,
    graph: AgentGraph,
    request: AgentInvestigationStartRequest,
    *,
    workflow_clock: WorkflowClock = utc_now,
    run_id_factory: RunIdFactory = generate_run_id,
    model_provider: str | None = None,
    model_name: str | None = None,
) -> AgentRunResponse:
    run_id = run_id_factory().strip()

    if not run_id:
        raise ValueError("The generated agent run ID must not be empty.")

    thread_id = request.thread_id or run_id
    started_at = _normalize_utc_timestamp(workflow_clock())

    run = AgentRun(
        id=run_id,
        thread_id=thread_id,
        user_query=request.user_query,
        status=AgentRunStatus.RUNNING,
        model_provider=model_provider,
        model_name=model_name,
        started_at=started_at,
    )
    _commit_run(
        database_session,
        run,
    )

    initial_state = create_initial_state(
        request.user_query,
        request.asset_code,
        max_iterations=request.max_iterations,
        run_id=run_id,
        thread_id=thread_id,
    )
    config: dict[str, object] = {
        "configurable": {
            "thread_id": thread_id,
        }
    }

    try:
        result = graph.invoke(
            initial_state,
            config=config,
        )
        (
            public_status,
            diagnosis,
            proposal,
            approval_interrupt,
            approval_decision,
            error_message,
        ) = _validate_graph_result(result)
    except Exception as error:
        completed_at = _normalize_utc_timestamp(workflow_clock())
        _record_execution_failure(
            database_session,
            run,
            error,
            completed_at=completed_at,
        )
        raise AgentWorkflowExecutionError(
            run_id,
            f"Agent run '{run_id}' failed during workflow execution.",
        ) from error

    run.status = public_status
    run.final_response = diagnosis.summary if diagnosis is not None else None
    run.error_message = error_message

    completed_at: datetime | None = None

    if public_status not in {
        AgentRunStatus.RUNNING,
        AgentRunStatus.WAITING_FOR_APPROVAL,
    }:
        completed_at = _normalize_utc_timestamp(workflow_clock())
        run.completed_at = completed_at
        run.duration_ms = _duration_ms(
            started_at,
            completed_at,
        )

    _commit_run(
        database_session,
        run,
    )

    return AgentRunResponse(
        run_id=run.id,
        thread_id=run.thread_id,
        status=run.status,
        started_at=run.started_at,
        completed_at=completed_at,
        diagnosis=diagnosis,
        work_order_proposal=proposal,
        approval_interrupt=approval_interrupt,
        approval_decision=approval_decision,
        final_response=run.final_response,
        error_type=run.error_type,
        error_message=run.error_message,
    )
