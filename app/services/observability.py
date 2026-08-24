from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.agent_log import (
    AgentRun,
    AgentStep,
    ToolCall,
)
from app.models.approval import Approval
from app.models.enums import (
    ApprovalDecision,
    ToolCallStatus,
)
from app.schemas.observability import (
    AgentStepRecordInput,
    ToolCallRecordInput,
)
from app.services.exceptions import (
    ObservabilityApprovalError,
    ObservabilityConflictError,
    ObservabilityPersistenceError,
    ObservabilityReferenceError,
)


def _load_agent_run(
    database_session: Session,
    run_id: str,
) -> AgentRun:
    try:
        run = database_session.get(
            AgentRun,
            run_id,
        )
    except SQLAlchemyError as error:
        database_session.rollback()
        raise ObservabilityPersistenceError("The observability agent-run query failed.") from error

    if run is None:
        raise ObservabilityReferenceError(f"Agent run '{run_id}' was not found for observability.")

    return run


def _load_agent_step(
    database_session: Session,
    step_id: int,
    run_id: str,
) -> AgentStep:
    try:
        step = database_session.get(
            AgentStep,
            step_id,
        )
    except SQLAlchemyError as error:
        database_session.rollback()
        raise ObservabilityPersistenceError("The observability agent-step query failed.") from error

    if step is None:
        raise ObservabilityReferenceError(
            f"Agent step '{step_id}' was not found for observability."
        )

    if step.run_id != run_id:
        raise ObservabilityReferenceError(
            f"Agent step '{step_id}' does not belong to run '{run_id}'."
        )

    return step


def _load_approval(
    database_session: Session,
    approval_id: int,
) -> Approval:
    try:
        approval = database_session.get(
            Approval,
            approval_id,
        )
    except SQLAlchemyError as error:
        database_session.rollback()
        raise ObservabilityPersistenceError("The observability approval query failed.") from error

    if approval is None:
        raise ObservabilityReferenceError(
            f"Approval '{approval_id}' was not found for observability."
        )

    return approval


def _commit_record(
    database_session: Session,
    record: AgentStep | ToolCall,
) -> None:
    try:
        database_session.add(record)
        database_session.commit()
        database_session.refresh(record)
    except SQLAlchemyError as error:
        database_session.rollback()
        raise ObservabilityPersistenceError(
            "The observability database transaction failed."
        ) from error


def get_next_agent_step_number(
    database_session: Session,
    run_id: str,
) -> int:
    _load_agent_run(
        database_session,
        run_id,
    )

    try:
        current_step_number = database_session.scalar(
            select(func.max(AgentStep.step_number)).where(
                AgentStep.run_id == run_id,
            )
        )
    except SQLAlchemyError as error:
        database_session.rollback()
        raise ObservabilityPersistenceError(
            "The observability step-number query failed."
        ) from error

    return (current_step_number or 0) + 1


def record_agent_step(
    database_session: Session,
    record_input: AgentStepRecordInput,
) -> AgentStep:
    _load_agent_run(
        database_session,
        record_input.run_id,
    )

    try:
        existing_step_id = database_session.scalar(
            select(AgentStep.id).where(
                AgentStep.run_id == record_input.run_id,
                AgentStep.step_number == record_input.step_number,
            )
        )
    except SQLAlchemyError as error:
        database_session.rollback()
        raise ObservabilityPersistenceError(
            "The observability agent-step conflict query failed."
        ) from error

    if existing_step_id is not None:
        raise ObservabilityConflictError(
            f"Agent run '{record_input.run_id}' already contains step '{record_input.step_number}'."
        )

    step = AgentStep(
        run_id=record_input.run_id,
        step_number=record_input.step_number,
        step_type=record_input.step_type,
        status=record_input.status,
        summary=record_input.summary,
        started_at=record_input.started_at,
        completed_at=record_input.completed_at,
        duration_ms=record_input.duration_ms,
        error_type=record_input.error_type,
        error_message=record_input.error_message,
    )

    _commit_record(
        database_session,
        step,
    )

    return step


def record_tool_call(
    database_session: Session,
    record_input: ToolCallRecordInput,
) -> ToolCall:
    _load_agent_run(
        database_session,
        record_input.run_id,
    )

    if record_input.step_id is not None:
        _load_agent_step(
            database_session,
            record_input.step_id,
            record_input.run_id,
        )

    approval: Approval | None = None

    if record_input.approval_id is not None:
        approval = _load_approval(
            database_session,
            record_input.approval_id,
        )

    if record_input.is_state_changing and record_input.status != ToolCallStatus.BLOCKED:
        if approval is None:
            raise ObservabilityApprovalError(
                "A non-blocked state-changing tool call requires approval."
            )

        if approval.decision != ApprovalDecision.APPROVED:
            raise ObservabilityApprovalError(f"Approval '{approval.id}' has not been approved.")

        if approval.approval_scope != "execute_work_order":
            raise ObservabilityApprovalError(
                f"Approval '{approval.id}' does not permit work-order execution."
            )

    tool_call = ToolCall(
        run_id=record_input.run_id,
        step_id=record_input.step_id,
        approval_id=record_input.approval_id,
        tool_name=record_input.tool_name,
        arguments_json=dict(record_input.arguments_json),
        result_json=(
            dict(record_input.result_json) if record_input.result_json is not None else None
        ),
        status=record_input.status,
        is_state_changing=record_input.is_state_changing,
        started_at=record_input.started_at,
        completed_at=record_input.completed_at,
        latency_ms=record_input.latency_ms,
        error_type=record_input.error_type,
        error_message=record_input.error_message,
    )

    _commit_record(
        database_session,
        tool_call,
    )

    return tool_call
