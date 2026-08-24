from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from langgraph.types import Command
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agent.state import (
    AgentStatus,
    create_initial_state,
)
from app.models.agent_log import AgentRun
from app.models.approval import Approval
from app.models.enums import AgentRunStatus
from app.models.work_order import WorkOrder
from app.schemas.actions import (
    WorkOrderApprovalDecisionInput,
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)
from app.schemas.agent_api import (
    AgentApprovalDecisionRequest,
    AgentInvestigationStartRequest,
    AgentRunResponse,
)
from app.schemas.diagnosis import (
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.hitl import (
    WorkOrderApprovalInterrupt,
    WorkOrderApprovalResume,
)
from app.services.approvals import decide_work_order_approval
from app.services.exceptions import (
    AgentRunApprovalStateError,
    AgentRunNotFoundError,
    AgentWorkflowExecutionError,
    AgentWorkflowPersistenceError,
    AgentWorkflowStateError,
)

WorkflowClock = Callable[[], datetime]
RunIdFactory = Callable[[], str]


class AgentGraphSnapshot(Protocol):
    values: Mapping[str, object]


class AgentGraph(Protocol):
    def invoke(
        self,
        input: object,
        *,
        config: dict[str, object],
    ) -> Mapping[str, object]: ...

    def get_state(
        self,
        config: dict[str, object],
    ) -> AgentGraphSnapshot: ...


def utc_now() -> datetime:
    return datetime.now(UTC)


def generate_run_id() -> str:
    return str(uuid4())


def _normalize_utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Agent workflow timestamps must include timezone information.")

    return value.astimezone(UTC)


def _restore_utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)

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


def _load_checkpoint_values(
    graph: AgentGraph,
    run: AgentRun,
) -> Mapping[str, object]:
    config: dict[str, object] = {
        "configurable": {
            "thread_id": run.thread_id,
        }
    }

    try:
        snapshot = graph.get_state(config)
    except Exception as error:
        if run.status == AgentRunStatus.FAILED:
            return {}

        raise AgentWorkflowStateError(
            f"Checkpoint state for agent run '{run.id}' could not be loaded."
        ) from error

    values = snapshot.values

    if not values:
        if run.status == AgentRunStatus.FAILED:
            return {}

        raise AgentWorkflowStateError(f"Checkpoint state for agent run '{run.id}' was not found.")

    if values.get("run_id") != run.id:
        raise AgentWorkflowStateError(
            "Checkpoint run identity does not match the persisted agent run."
        )

    if values.get("thread_id") != run.thread_id:
        raise AgentWorkflowStateError(
            "Checkpoint thread identity does not match the persisted agent run."
        )

    return values


def get_agent_run(
    database_session: Session,
    graph: AgentGraph,
    run_id: str,
) -> AgentRunResponse:
    normalized_run_id = run_id.strip()

    if not normalized_run_id:
        raise AgentRunNotFoundError(run_id)

    try:
        run = database_session.get(
            AgentRun,
            normalized_run_id,
        )
    except SQLAlchemyError as error:
        database_session.rollback()
        raise AgentWorkflowPersistenceError("The agent-run database query failed.") from error

    if run is None:
        raise AgentRunNotFoundError(normalized_run_id)

    checkpoint_values = _load_checkpoint_values(
        graph,
        run,
    )

    diagnosis: MaintenanceDiagnosis | None = None
    proposal: WorkOrderProposalOutput | None = None
    approval_interrupt: WorkOrderApprovalInterrupt | None = None
    approval_decision: WorkOrderApprovalDecisionOutput | None = None

    if checkpoint_values:
        if run.status == AgentRunStatus.FAILED:
            diagnosis = _validate_optional_model(
                MaintenanceDiagnosis,
                checkpoint_values.get("diagnosis"),
            )
            proposal = _validate_optional_model(
                WorkOrderProposalOutput,
                checkpoint_values.get("work_order_proposal"),
            )
            approval_interrupt = _validate_optional_model(
                WorkOrderApprovalInterrupt,
                checkpoint_values.get("approval_interrupt"),
            )
            approval_decision = _validate_optional_model(
                WorkOrderApprovalDecisionOutput,
                checkpoint_values.get("approval_decision"),
            )
        else:
            (
                checkpoint_status,
                diagnosis,
                proposal,
                approval_interrupt,
                approval_decision,
                _checkpoint_error,
            ) = _validate_graph_result(checkpoint_values)

            if checkpoint_status != run.status:
                raise AgentWorkflowStateError(
                    "Checkpoint status does not match the persisted agent-run status."
                )

    completed_at = (
        _restore_utc_timestamp(run.completed_at) if run.completed_at is not None else None
    )

    return AgentRunResponse(
        run_id=run.id,
        thread_id=run.thread_id,
        status=run.status,
        started_at=_restore_utc_timestamp(run.started_at),
        completed_at=completed_at,
        diagnosis=diagnosis,
        work_order_proposal=proposal,
        approval_interrupt=approval_interrupt,
        approval_decision=approval_decision,
        final_response=run.final_response,
        error_type=run.error_type,
        error_message=run.error_message,
    )


def _load_agent_run_record(
    database_session: Session,
    run_id: str,
) -> AgentRun:
    normalized_run_id = run_id.strip()

    if not normalized_run_id:
        raise AgentRunNotFoundError(run_id)

    try:
        run = database_session.get(
            AgentRun,
            normalized_run_id,
        )
    except SQLAlchemyError as error:
        database_session.rollback()
        raise AgentWorkflowPersistenceError("The agent-run database query failed.") from error

    if run is None:
        raise AgentRunNotFoundError(normalized_run_id)

    return run


def _validate_approval_database_identity(
    database_session: Session,
    proposal: WorkOrderProposalOutput,
) -> None:
    try:
        work_order = database_session.get(
            WorkOrder,
            proposal.work_order_id,
        )
        approval = database_session.get(
            Approval,
            proposal.approval_id,
        )
    except SQLAlchemyError as error:
        database_session.rollback()
        raise AgentWorkflowPersistenceError(
            "The approval identity database query failed."
        ) from error

    if work_order is None:
        raise AgentWorkflowStateError("The checkpoint work order does not exist.")

    if approval is None:
        raise AgentWorkflowStateError("The checkpoint approval record does not exist.")

    if work_order.work_order_number != proposal.work_order_number:
        raise AgentWorkflowStateError("Checkpoint work-order number does not match the database.")

    if work_order.revision != proposal.revision:
        raise AgentWorkflowStateError("Checkpoint work-order revision does not match the database.")

    if approval.work_order_id != proposal.work_order_id:
        raise AgentWorkflowStateError(
            "Checkpoint approval does not belong to the proposed work order."
        )

    if approval.request_version != proposal.request_version:
        raise AgentWorkflowStateError("Checkpoint approval version does not match the database.")

    if approval.approval_scope != proposal.approval_scope:
        raise AgentWorkflowStateError("Checkpoint approval scope does not match the database.")


def _record_resume_failure(
    database_session: Session,
    run: AgentRun,
    error: Exception,
) -> None:
    run.status = AgentRunStatus.WAITING_FOR_APPROVAL
    run.completed_at = None
    run.duration_ms = None
    run.error_type = type(error).__name__
    run.error_message = str(error)[:4000]

    _commit_run(
        database_session,
        run,
    )


def decide_agent_run_approval(
    database_session: Session,
    graph: AgentGraph,
    run_id: str,
    request: AgentApprovalDecisionRequest,
    *,
    workflow_clock: WorkflowClock = utc_now,
) -> AgentRunResponse:
    run = _load_agent_run_record(
        database_session,
        run_id,
    )

    if run.status != AgentRunStatus.WAITING_FOR_APPROVAL:
        raise AgentRunApprovalStateError(f"Agent run '{run.id}' is not waiting for approval.")

    checkpoint_values = _load_checkpoint_values(
        graph,
        run,
    )
    (
        checkpoint_status,
        diagnosis,
        proposal,
        approval_interrupt,
        _existing_decision,
        _checkpoint_error,
    ) = _validate_graph_result(checkpoint_values)

    if checkpoint_status != AgentRunStatus.WAITING_FOR_APPROVAL:
        raise AgentWorkflowStateError("Checkpoint is not waiting for an approval decision.")

    if proposal is None or approval_interrupt is None:
        raise AgentWorkflowStateError("Approval resume requires a trusted proposal and interrupt.")

    _validate_approval_database_identity(
        database_session,
        proposal,
    )

    decision_input = WorkOrderApprovalDecisionInput(
        work_order_id=proposal.work_order_id,
        request_version=request.request_version,
        decision=request.decision,
        decided_by=request.decided_by,
        decision_reason=request.decision_reason,
        decision_source=request.decision_source,
        approval_scope=request.approval_scope,
    )
    decision_output = decide_work_order_approval(
        database_session,
        decision_input,
        decision_clock=workflow_clock,
    )
    resume_payload = WorkOrderApprovalResume(
        run_id=run.id,
        thread_id=run.thread_id,
        decision=decision_output,
    )
    config: dict[str, object] = {
        "configurable": {
            "thread_id": run.thread_id,
        }
    }

    try:
        resumed_result = graph.invoke(
            Command(
                resume=resume_payload.model_dump(mode="json"),
            ),
            config=config,
        )
        (
            resumed_status,
            resumed_diagnosis,
            resumed_proposal,
            resumed_interrupt,
            resumed_decision,
            resumed_error,
        ) = _validate_graph_result(resumed_result)

        if resumed_status != AgentRunStatus.COMPLETED:
            raise AgentWorkflowStateError("Approval resume did not complete the agent run.")

        if resumed_decision != decision_output:
            raise AgentWorkflowStateError(
                "Resumed approval decision does not match the applied decision."
            )
    except Exception as error:
        _record_resume_failure(
            database_session,
            run,
            error,
        )
        raise AgentWorkflowExecutionError(
            run.id,
            f"Agent run '{run.id}' failed during approval resume.",
        ) from error

    completed_at = _normalize_utc_timestamp(workflow_clock())
    run.status = AgentRunStatus.COMPLETED
    run.completed_at = completed_at
    run.duration_ms = _duration_ms(
        _restore_utc_timestamp(run.started_at),
        completed_at,
    )
    run.final_response = (
        resumed_diagnosis.summary if resumed_diagnosis is not None else run.final_response
    )
    run.error_type = None
    run.error_message = resumed_error

    _commit_run(
        database_session,
        run,
    )

    return AgentRunResponse(
        run_id=run.id,
        thread_id=run.thread_id,
        status=run.status,
        started_at=_restore_utc_timestamp(run.started_at),
        completed_at=completed_at,
        diagnosis=resumed_diagnosis,
        work_order_proposal=resumed_proposal,
        approval_interrupt=resumed_interrupt,
        approval_decision=resumed_decision,
        final_response=run.final_response,
        error_type=run.error_type,
        error_message=run.error_message,
    )


def _validate_approval_database_identity(
    database_session: Session,
    proposal: WorkOrderProposalOutput,
) -> None:
    try:
        work_order = database_session.get(
            WorkOrder,
            proposal.work_order_id,
        )
        approval = database_session.get(
            Approval,
            proposal.approval_id,
        )
    except SQLAlchemyError as error:
        database_session.rollback()
        raise AgentWorkflowPersistenceError(
            "The approval identity database query failed."
        ) from error

    if work_order is None:
        raise AgentWorkflowStateError("The checkpoint work order does not exist.")

    if approval is None:
        raise AgentWorkflowStateError("The checkpoint approval record does not exist.")

    if work_order.work_order_number != proposal.work_order_number:
        raise AgentWorkflowStateError("Checkpoint work-order number does not match the database.")

    if work_order.revision != proposal.revision:
        raise AgentWorkflowStateError("Checkpoint work-order revision does not match the database.")

    if approval.work_order_id != proposal.work_order_id:
        raise AgentWorkflowStateError(
            "Checkpoint approval does not belong to the proposed work order."
        )

    if approval.request_version != proposal.request_version:
        raise AgentWorkflowStateError("Checkpoint approval version does not match the database.")

    if approval.approval_scope != proposal.approval_scope:
        raise AgentWorkflowStateError("Checkpoint approval scope does not match the database.")


def _record_resume_failure(
    database_session: Session,
    run: AgentRun,
    error: Exception,
) -> None:
    run.status = AgentRunStatus.WAITING_FOR_APPROVAL
    run.completed_at = None
    run.duration_ms = None
    run.error_type = type(error).__name__
    run.error_message = str(error)[:4000]

    _commit_run(
        database_session,
        run,
    )
