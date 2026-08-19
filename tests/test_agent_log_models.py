from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.models import AgentRun, AgentStep, ToolCall
from app.models.common import utc_now
from app.models.enums import (
    AgentStepStatus,
    AgentStepType,
    ToolCallStatus,
)


def test_agent_run_step_and_tool_call_can_be_persisted() -> None:
    test_engine = create_database_engine("sqlite+pysqlite:///:memory:")

    try:
        Base.metadata.create_all(test_engine)

        with Session(test_engine) as database_session:
            agent_run = AgentRun(
                thread_id="test-thread-001",
                user_query="Investigate elevated vibration on P-101.",
            )
            agent_step = AgentStep(
                run=agent_run,
                step_number=1,
                step_type=AgentStepType.TOOL_EXECUTION,
                status=AgentStepStatus.COMPLETED,
                summary="Retrieved P-101 asset details.",
                completed_at=utc_now(),
                duration_ms=12,
            )
            tool_call = ToolCall(
                run=agent_run,
                step=agent_step,
                tool_name="get_asset_details",
                arguments_json={"asset_code": "P-101"},
                result_json={
                    "asset_code": "P-101",
                    "status": "operational",
                },
                status=ToolCallStatus.SUCCEEDED,
                completed_at=utc_now(),
                latency_ms=8,
            )

            database_session.add(tool_call)
            database_session.commit()
            database_session.refresh(agent_run)
            database_session.refresh(agent_step)
            database_session.refresh(tool_call)

            assert agent_run.id is not None
            assert agent_run.model_calls == 0
            assert agent_step.run_id == agent_run.id
            assert tool_call.run_id == agent_run.id
            assert tool_call.step_id == agent_step.id
            assert tool_call.arguments_json == {"asset_code": "P-101"}
            assert tool_call.is_state_changing is False
    finally:
        Base.metadata.drop_all(test_engine)
        test_engine.dispose()
