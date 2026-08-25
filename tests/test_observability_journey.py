from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.graph import build_agent_graph
from app.db.base import Base
from app.db.session import create_database_engine
from app.models.agent_log import (
    AgentRun,
    AgentStep,
    ToolCall,
)
from app.models.approval import Approval
from app.models.enums import (
    AgentRunStatus,
    AgentStepStatus,
    AgentStepType,
    ToolCallStatus,
)
from app.models.work_order import WorkOrder
from app.schemas.agent_api import (
    AgentInvestigationStartRequest,
)
from app.schemas.asset import AssetDetailsInput
from app.services.agent_workflows import (
    start_agent_investigation,
)
from app.services.exceptions import (
    AgentWorkflowExecutionError,
)

RUN_STARTED_AT = datetime(
    2026,
    8,
    25,
    16,
    0,
    tzinfo=UTC,
)
RUN_COMPLETED_AT = RUN_STARTED_AT + timedelta(seconds=1)


@pytest.fixture
def database_session_factory(
    tmp_path: Path,
) -> Generator[sessionmaker[Session], None, None]:
    database_path = tmp_path / "observability_journey.sqlite"
    engine = create_database_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    yield factory

    Base.metadata.drop_all(engine)
    engine.dispose()


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
        description=("Retrieve details for one maintenance asset."),
        args_schema=AssetDetailsInput,
    )


def create_asset_tool_request() -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "get_asset_details",
                "args": {
                    "asset_code": "P-101",
                },
                "id": "journey-asset-call-1",
                "type": "tool_call",
            }
        ],
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        },
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
        "description": ("Synthetic main cooling-water pump."),
        "parent_asset_code": None,
        "child_asset_codes": ["M-101"],
    }


def create_request() -> AgentInvestigationStartRequest:
    return AgentInvestigationStartRequest(
        user_query=("Investigate increasing vibration on P-101."),
        asset_code="P-101",
        max_iterations=3,
    )


def test_successful_investigation_persists_complete_observability_journey(
    database_session_factory: sessionmaker[Session],
) -> None:
    run_id = "run-observability-journey-001"
    model = Mock()
    model.invoke.side_effect = [
        create_asset_tool_request(),
        AIMessage(
            content=("Asset evidence was retrieved; additional evidence is required."),
            usage_metadata={
                "input_tokens": 80,
                "output_tokens": 15,
                "total_tokens": 95,
            },
        ),
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
    workflow_clock = Mock(
        side_effect=[
            RUN_STARTED_AT,
            RUN_COMPLETED_AT,
        ]
    )

    with database_session_factory() as database_session:
        response = start_agent_investigation(
            database_session,
            graph,
            create_request(),
            workflow_clock=workflow_clock,
            run_id_factory=lambda: run_id,
            model_provider="azure_openai",
            model_name="gpt-5.4-mini",
        )

    with database_session_factory() as database_session:
        persisted_run = database_session.get(
            AgentRun,
            run_id,
        )
        steps = list(
            database_session.scalars(
                select(AgentStep)
                .where(
                    AgentStep.run_id == run_id,
                )
                .order_by(
                    AgentStep.step_number,
                )
            )
        )
        tool_calls = list(
            database_session.scalars(
                select(ToolCall).where(
                    ToolCall.run_id == run_id,
                )
            )
        )
        work_order_count = database_session.scalar(select(func.count()).select_from(WorkOrder))
        approval_count = database_session.scalar(select(func.count()).select_from(Approval))

    assert response.run_id == run_id
    assert response.status == AgentRunStatus.COMPLETED
    assert response.completed_at == RUN_COMPLETED_AT

    assert persisted_run is not None
    assert persisted_run.status == AgentRunStatus.COMPLETED
    assert persisted_run.model_provider == "azure_openai"
    assert persisted_run.model_name == "gpt-5.4-mini"
    assert persisted_run.model_calls == 2
    assert persisted_run.prompt_tokens == 180
    assert persisted_run.completion_tokens == 35
    assert persisted_run.total_tokens == 215
    assert persisted_run.estimated_cost_usd == 0.0
    assert persisted_run.duration_ms == 1000

    assert [step.step_type for step in steps] == [
        AgentStepType.ROUTING,
        AgentStepType.GUARDRAIL,
        AgentStepType.TOOL_SELECTION,
        AgentStepType.TOOL_EXECUTION,
        AgentStepType.TOOL_SELECTION,
    ]
    assert all(step.status == AgentStepStatus.COMPLETED for step in steps)

    assert len(tool_calls) == 1
    assert tool_calls[0].status == ToolCallStatus.SUCCEEDED
    assert tool_calls[0].tool_name == ("get_asset_details")
    assert tool_calls[0].arguments_json == {
        "asset_code": "P-101",
    }
    assert tool_calls[0].result_json["asset_code"] == "P-101"
    assert tool_calls[0].is_state_changing is False
    assert tool_calls[0].step_id == steps[3].id

    assert work_order_count == 0
    assert approval_count == 0
    tool_function.assert_called_once_with(asset_code="P-101")


def test_failed_model_investigation_persists_failure_observability(
    database_session_factory: sessionmaker[Session],
) -> None:
    run_id = "run-observability-failure-001"
    model = Mock()
    model.invoke.side_effect = RuntimeError("Synthetic hosted-model failure.")
    graph = build_agent_graph(
        model,
        observability_session_factory=(database_session_factory),
    )
    workflow_clock = Mock(
        side_effect=[
            RUN_STARTED_AT,
            RUN_COMPLETED_AT,
        ]
    )

    with database_session_factory() as database_session:
        with pytest.raises(
            AgentWorkflowExecutionError,
            match="failed during workflow execution",
        ) as captured_error:
            start_agent_investigation(
                database_session,
                graph,
                create_request(),
                workflow_clock=workflow_clock,
                run_id_factory=lambda: run_id,
                model_provider="azure_openai",
                model_name="gpt-5.4-mini",
            )

    with database_session_factory() as database_session:
        persisted_run = database_session.get(
            AgentRun,
            run_id,
        )
        steps = list(
            database_session.scalars(
                select(AgentStep)
                .where(
                    AgentStep.run_id == run_id,
                )
                .order_by(
                    AgentStep.step_number,
                )
            )
        )
        tool_call_count = database_session.scalar(select(func.count()).select_from(ToolCall))

    assert captured_error.value.run_id == run_id

    assert persisted_run is not None
    assert persisted_run.status == AgentRunStatus.FAILED
    assert persisted_run.completed_at is not None
    assert persisted_run.duration_ms == 1000
    assert persisted_run.model_calls == 1
    assert persisted_run.prompt_tokens == 0
    assert persisted_run.completion_tokens == 0
    assert persisted_run.total_tokens == 0
    assert persisted_run.estimated_cost_usd == 0.0
    assert persisted_run.error_type == "RuntimeError"
    assert persisted_run.error_message == ("Synthetic hosted-model failure.")

    assert [step.step_type for step in steps] == [
        AgentStepType.ROUTING,
        AgentStepType.GUARDRAIL,
        AgentStepType.TOOL_SELECTION,
    ]
    assert steps[-1].status == AgentStepStatus.FAILED
    assert steps[-1].error_type == "RuntimeError"
    assert steps[-1].error_message == ("Synthetic hosted-model failure.")
    assert tool_call_count == 0
