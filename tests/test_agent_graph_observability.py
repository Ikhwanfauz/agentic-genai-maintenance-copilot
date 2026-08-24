from collections.abc import Generator
from datetime import UTC, date, datetime
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
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
    ToolCall,
)
from app.models.enums import (
    AgentRunStatus,
    AgentStepStatus,
    AgentStepType,
    ToolCallStatus,
)
from app.schemas.asset import AssetDetailsInput

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


def load_tool_calls(
    session_factory: sessionmaker[Session],
) -> list[ToolCall]:
    with session_factory() as database_session:
        return list(database_session.scalars(select(ToolCall).order_by(ToolCall.id)))


def create_asset_tool(
    function: Mock,
) -> StructuredTool:
    def run_get_asset_details(
        asset_code: str,
    ) -> dict[str, object]:
        result = function(
            asset_code=asset_code,
        )
        return dict(result)

    return StructuredTool.from_function(
        func=run_get_asset_details,
        name="get_asset_details",
        description="Retrieve details for one maintenance asset.",
        args_schema=AssetDetailsInput,
    )


def create_asset_tool_call() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_asset_details",
                "args": {
                    "asset_code": "P-101",
                },
                "id": "asset-call-observe-1",
                "type": "tool_call",
            }
        ],
    )


def create_asset_result() -> dict[str, object]:
    return {
        "id": 1,
        "asset_code": "P-101",
        "name": "Main Cooling Water Pump",
        "asset_type": "pump",
        "status": "operational",
        "criticality": "critical",
        "location": "Utilities Area",
        "manufacturer": "FlowServe Simulation",
        "model_number": "CS-200",
        "installation_date": date(
            2021,
            6,
            15,
        ).isoformat(),
        "description": "Synthetic cooling-water pump.",
        "parent_asset_code": None,
        "child_asset_codes": ["M-101"],
    }


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


def test_agent_graph_persists_successful_tool_call(
    database_session_factory: sessionmaker[Session],
) -> None:
    run_id = "run-tool-observe-001"
    create_run(
        database_session_factory,
        run_id,
    )
    model = Mock()
    model.invoke.side_effect = [
        create_asset_tool_call(),
        AIMessage(content="Asset evidence was retrieved."),
    ]
    tool_function = Mock(
        return_value=create_asset_result(),
    )
    graph = build_agent_graph(
        model,
        [
            create_asset_tool(
                tool_function,
            )
        ],
        observability_session_factory=(database_session_factory),
    )

    result = graph.invoke(
        create_initial_state(
            "Investigate P-101 vibration.",
            "P-101",
            max_iterations=3,
            run_id=run_id,
        )
    )

    steps = load_steps(
        database_session_factory,
    )
    tool_calls = load_tool_calls(
        database_session_factory,
    )
    execution_step = next(step for step in steps if step.step_type == AgentStepType.TOOL_EXECUTION)

    assert result["status"] == AgentStatus.COMPLETED
    assert len(tool_calls) == 1
    assert tool_calls[0].step_id == execution_step.id
    assert tool_calls[0].tool_name == "get_asset_details"
    assert tool_calls[0].arguments_json == {
        "asset_code": "P-101",
    }
    assert tool_calls[0].result_json["asset_code"] == "P-101"
    assert tool_calls[0].status == ToolCallStatus.SUCCEEDED
    assert tool_calls[0].is_state_changing is False
    tool_function.assert_called_once_with(asset_code="P-101")


def test_agent_graph_persists_handled_tool_failure(
    database_session_factory: sessionmaker[Session],
) -> None:
    run_id = "run-tool-observe-002"
    create_run(
        database_session_factory,
        run_id,
    )
    model = Mock()
    model.invoke.side_effect = [
        create_asset_tool_call(),
        AIMessage(content="The tool failed; further evidence is required."),
    ]
    tool_function = Mock(side_effect=RuntimeError("Synthetic asset database failure."))
    graph = build_agent_graph(
        model,
        [
            create_asset_tool(
                tool_function,
            )
        ],
        observability_session_factory=(database_session_factory),
    )

    result = graph.invoke(
        create_initial_state(
            "Investigate P-101 vibration.",
            "P-101",
            max_iterations=3,
            run_id=run_id,
        )
    )

    tool_calls = load_tool_calls(
        database_session_factory,
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert len(tool_calls) == 1
    assert tool_calls[0].status == ToolCallStatus.FAILED
    assert tool_calls[0].result_json is None
    assert tool_calls[0].error_type == "ToolExecutionError"
    assert "Synthetic asset database failure" in (tool_calls[0].error_message or "")
