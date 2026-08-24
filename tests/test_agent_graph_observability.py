from collections.abc import Generator
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.graph import build_agent_graph
from app.agent.state import (
    AgentStatus,
    create_initial_state,
)
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

STARTED_AT = datetime(2026, 8, 25, 15, 0, tzinfo=UTC)


@pytest.fixture
def database_session_factory() -> Generator[sessionmaker[Session], None, None]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    yield factory

    Base.metadata.drop_all(engine)
    engine.dispose()


def create_run(
    session_factory: sessionmaker[Session],
    run_id: str,
) -> None:
    with session_factory() as database_session:
        database_session.add(
            AgentRun(
                id=run_id,
                thread_id=run_id,
                user_query="Investigate P-101 vibration.",
                status=AgentRunStatus.RUNNING,
                started_at=STARTED_AT,
            )
        )
        database_session.commit()


def load_steps(
    session_factory: sessionmaker[Session],
) -> list[AgentStep]:
    with session_factory() as database_session:
        return list(database_session.scalars(select(AgentStep).order_by(AgentStep.step_number)))


def test_agent_graph_persists_completed_node_sequence(
    database_session_factory: sessionmaker[Session],
) -> None:
    run_id = "run-graph-observe-001"
    create_run(
        database_session_factory,
        run_id,
    )
    model = Mock()
    model.invoke.return_value = AIMessage(content="Additional evidence is required.")
    graph = build_agent_graph(
        model,
        observability_session_factory=(database_session_factory),
    )

    result = graph.invoke(
        create_initial_state(
            "Investigate P-101 vibration.",
            "P-101",
            run_id=run_id,
        )
    )

    steps = load_steps(
        database_session_factory,
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert [step.step_number for step in steps] == [1, 2, 3]
    assert [step.step_type for step in steps] == [
        AgentStepType.ROUTING,
        AgentStepType.GUARDRAIL,
        AgentStepType.TOOL_SELECTION,
    ]
    assert all(step.status == AgentStepStatus.COMPLETED for step in steps)


def test_agent_graph_persists_failed_model_node(
    database_session_factory: sessionmaker[Session],
) -> None:
    run_id = "run-graph-observe-002"
    create_run(
        database_session_factory,
        run_id,
    )
    model = Mock()
    model.invoke.side_effect = RuntimeError("Synthetic hosted-model failure.")
    graph = build_agent_graph(
        model,
        observability_session_factory=(database_session_factory),
    )

    with pytest.raises(
        RuntimeError,
        match="Synthetic hosted-model failure",
    ):
        graph.invoke(
            create_initial_state(
                "Investigate P-101 vibration.",
                "P-101",
                run_id=run_id,
            )
        )

    steps = load_steps(
        database_session_factory,
    )

    assert [step.step_number for step in steps] == [1, 2, 3]
    assert steps[-1].step_type == AgentStepType.TOOL_SELECTION
    assert steps[-1].status == AgentStepStatus.FAILED
    assert steps[-1].error_type == "RuntimeError"
    assert steps[-1].error_message == "Synthetic hosted-model failure."
