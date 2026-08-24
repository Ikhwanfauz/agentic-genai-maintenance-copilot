from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.observability import create_observed_node
from app.agent.state import create_initial_state
from app.db.base import Base
from app.db.session import create_database_engine
from app.models.agent_log import (
    AgentRun,
    AgentStep,
)
from app.models.enums import (
    AgentRunStatus,
    AgentStepStatus,
    AgentStepType,
)

STARTED_AT = datetime(2026, 8, 25, 14, 0, tzinfo=UTC)
COMPLETED_AT = STARTED_AT + timedelta(milliseconds=25)


@pytest.fixture
def database_session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    with factory() as database_session:
        database_session.add(
            AgentRun(
                id="run-observed-001",
                thread_id="thread-observed-001",
                user_query="Investigate P-101 vibration.",
                status=AgentRunStatus.RUNNING,
                started_at=STARTED_AT,
            )
        )
        database_session.commit()

    yield factory

    Base.metadata.drop_all(engine)
    engine.dispose()


def create_state():
    return create_initial_state(
        "Investigate P-101 vibration.",
        "P-101",
        run_id="run-observed-001",
        thread_id="thread-observed-001",
    )


def test_observed_node_preserves_result_and_records_completed_step(
    database_session_factory: sessionmaker[Session],
) -> None:
    node_result = {
        "visited_nodes": ["mark_ready"],
    }
    node = Mock(
        return_value=node_result,
    )
    clock = Mock(
        side_effect=[
            STARTED_AT,
            COMPLETED_AT,
        ]
    )
    observed_node = create_observed_node(
        node,
        database_session_factory,
        step_type=AgentStepType.ROUTING,
        summary="  Prepared   investigation routing. ",
        observability_clock=clock,
    )
    state = create_state()

    result = observed_node(state)

    assert result is node_result
    node.assert_called_once_with(state)

    with database_session_factory() as database_session:
        step = database_session.scalar(select(AgentStep))

        assert step is not None
        assert step.run_id == "run-observed-001"
        assert step.step_number == 1
        assert step.step_type == AgentStepType.ROUTING
        assert step.status == AgentStepStatus.COMPLETED
        assert step.summary == "Prepared investigation routing."
        assert step.duration_ms == 25
        assert step.error_type is None
        assert step.error_message is None


def test_observed_node_records_failure_and_reraises_original_error(
    database_session_factory: sessionmaker[Session],
) -> None:
    node_error = RuntimeError("Diagnosis model unavailable.")
    node = Mock(
        side_effect=node_error,
    )
    clock = Mock(
        side_effect=[
            STARTED_AT,
            COMPLETED_AT,
        ]
    )
    observed_node = create_observed_node(
        node,
        database_session_factory,
        step_type=AgentStepType.EVIDENCE_SYNTHESIS,
        summary="Synthesized grounded diagnosis.",
        observability_clock=clock,
    )

    with pytest.raises(
        RuntimeError,
        match="Diagnosis model unavailable",
    ) as captured_error:
        observed_node(
            create_state(),
        )

    assert captured_error.value is node_error

    with database_session_factory() as database_session:
        step = database_session.scalar(select(AgentStep))

        assert step is not None
        assert step.status == AgentStepStatus.FAILED
        assert step.error_type == "RuntimeError"
        assert step.error_message == "Diagnosis model unavailable."
        assert step.duration_ms == 25


def test_observed_node_assigns_monotonic_step_numbers(
    database_session_factory: sessionmaker[Session],
) -> None:
    clock = Mock(
        side_effect=[
            STARTED_AT,
            COMPLETED_AT,
            COMPLETED_AT,
            COMPLETED_AT + timedelta(milliseconds=10),
        ]
    )
    observed_node = create_observed_node(
        Mock(
            return_value={
                "visited_nodes": ["call_model"],
            }
        ),
        database_session_factory,
        step_type=AgentStepType.TOOL_SELECTION,
        summary="Selected the next investigation action.",
        observability_clock=clock,
    )
    state = create_state()

    observed_node(state)
    observed_node(state)

    with database_session_factory() as database_session:
        step_numbers = list(
            database_session.scalars(select(AgentStep.step_number).order_by(AgentStep.step_number))
        )

    assert step_numbers == [1, 2]


def test_observed_node_rejects_empty_summary(
    database_session_factory: sessionmaker[Session],
) -> None:
    with pytest.raises(
        ValueError,
        match="requires a summary",
    ):
        create_observed_node(
            Mock(),
            database_session_factory,
            step_type=AgentStepType.ROUTING,
            summary="   ",
        )
