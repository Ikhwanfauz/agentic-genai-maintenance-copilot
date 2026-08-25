from collections.abc import Callable
from datetime import datetime
from typing import TypeAlias

from sqlalchemy.orm import Session

from app.agent.state import AgentState
from app.models.agent_log import AgentStep
from app.models.common import utc_now
from app.models.enums import (
    AgentStepStatus,
    AgentStepType,
)
from app.schemas.observability import AgentStepRecordInput
from app.services.observability import (
    get_next_agent_step_number,
    record_agent_step,
)

AgentNode: TypeAlias = Callable[
    [AgentState],
    dict[str, object],
]
DatabaseSessionFactory: TypeAlias = Callable[[], Session]
ObservabilityClock: TypeAlias = Callable[[], datetime]
ObservedNodeSuccess: TypeAlias = Callable[
    [
        AgentState,
        dict[str, object],
        AgentStep,
        datetime,
        datetime,
    ],
    None,
]
ObservedNodeFailure: TypeAlias = Callable[
    [
        AgentState,
        Exception,
        AgentStep,
        datetime,
        datetime,
    ],
    None,
]


def _duration_ms(
    started_at: datetime,
    completed_at: datetime,
) -> int:
    return max(
        0,
        round((completed_at - started_at).total_seconds() * 1000),
    )


def _persist_step(
    session_factory: DatabaseSessionFactory,
    *,
    run_id: str,
    step_type: AgentStepType,
    status: AgentStepStatus,
    summary: str,
    started_at: datetime,
    completed_at: datetime,
    error: Exception | None = None,
) -> AgentStep:
    with session_factory() as database_session:
        step_number = get_next_agent_step_number(
            database_session,
            run_id,
        )
        return record_agent_step(
            database_session,
            AgentStepRecordInput(
                run_id=run_id,
                step_number=step_number,
                step_type=step_type,
                status=status,
                summary=summary,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=_duration_ms(
                    started_at,
                    completed_at,
                ),
                error_type=(type(error).__name__[:150] if error is not None else None),
                error_message=(str(error)[:4000] if error is not None else None),
            ),
        )


def create_observed_node(
    node: AgentNode,
    session_factory: DatabaseSessionFactory,
    *,
    step_type: AgentStepType,
    summary: str,
    observability_clock: ObservabilityClock = utc_now,
    on_success: ObservedNodeSuccess | None = None,
    on_failure: ObservedNodeFailure | None = None,
) -> AgentNode:
    normalized_summary = " ".join(summary.split())

    if not normalized_summary:
        raise ValueError("An observed agent node requires a summary.")

    def observed_node(
        state: AgentState,
    ) -> dict[str, object]:
        started_at = observability_clock()

        try:
            result = node(state)
        except Exception as error:
            completed_at = observability_clock()

            try:
                step = _persist_step(
                    session_factory,
                    run_id=state["run_id"],
                    step_type=step_type,
                    status=AgentStepStatus.FAILED,
                    summary=normalized_summary,
                    started_at=started_at,
                    completed_at=completed_at,
                    error=error,
                )

                if on_failure is not None:
                    on_failure(
                        state,
                        error,
                        step,
                        started_at,
                        completed_at,
                    )
            except Exception as observability_error:
                error.add_note(
                    f"Agent-step observability persistence also failed: {observability_error}"
                )

            raise

        completed_at = observability_clock()
        step = _persist_step(
            session_factory,
            run_id=state["run_id"],
            step_type=step_type,
            status=AgentStepStatus.COMPLETED,
            summary=normalized_summary,
            started_at=started_at,
            completed_at=completed_at,
        )

        if on_success is not None:
            on_success(
                state,
                result,
                step,
                started_at,
                completed_at,
            )

        return result

    return observed_node
