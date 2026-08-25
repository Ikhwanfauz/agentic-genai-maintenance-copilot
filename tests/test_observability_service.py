from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.session import create_database_engine
from app.models.agent_log import (
    AgentRun,
    AgentStep,
    ToolCall,
)
from app.models.approval import Approval
from app.models.asset import Asset
from app.models.enums import (
    AgentRunStatus,
    AgentStepStatus,
    AgentStepType,
    ApprovalDecision,
    AssetStatus,
    AssetType,
    Criticality,
    ToolCallStatus,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.models.work_order import WorkOrder
from app.schemas.observability import (
    AgentStepRecordInput,
    ModelUsageRecordInput,
    ToolCallRecordInput,
)
from app.services.exceptions import (
    ObservabilityApprovalError,
    ObservabilityConflictError,
    ObservabilityReferenceError,
)
from app.services.observability import (
    record_agent_step,
    record_model_usage,
    record_tool_call,
)

STARTED_AT = datetime(2026, 8, 25, 13, 0, tzinfo=UTC)
COMPLETED_AT = STARTED_AT + timedelta(milliseconds=20)


@pytest.fixture
def database_session() -> Generator[Session, None, None]:
    engine = create_database_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        session.add_all(
            [
                AgentRun(
                    id="run-observe-001",
                    thread_id="thread-observe-001",
                    user_query="Investigate P-101 vibration.",
                    status=AgentRunStatus.RUNNING,
                    started_at=STARTED_AT,
                ),
                AgentRun(
                    id="run-observe-002",
                    thread_id="thread-observe-002",
                    user_query="Investigate P-102 condition.",
                    status=AgentRunStatus.RUNNING,
                    started_at=STARTED_AT,
                ),
            ]
        )
        session.commit()

        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def create_step_input(
    *,
    run_id: str = "run-observe-001",
    step_number: int = 1,
) -> AgentStepRecordInput:
    return AgentStepRecordInput(
        run_id=run_id,
        step_number=step_number,
        step_type=AgentStepType.ROUTING,
        status=AgentStepStatus.COMPLETED,
        summary="Initialized the maintenance investigation.",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        duration_ms=20,
    )


def create_tool_call_input(
    *,
    run_id: str = "run-observe-001",
    step_id: int | None = None,
) -> ToolCallRecordInput:
    return ToolCallRecordInput(
        run_id=run_id,
        step_id=step_id,
        tool_name="get_asset_details",
        arguments_json={"asset_code": "P-101"},
        result_json={
            "asset_code": "P-101",
            "status": "operational",
        },
        status=ToolCallStatus.SUCCEEDED,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        latency_ms=20,
    )


def create_approval(
    database_session: Session,
    *,
    decision: ApprovalDecision = ApprovalDecision.APPROVED,
    approval_scope: str = "execute_work_order",
) -> Approval:
    asset = Asset(
        asset_code="P-101",
        name="Main Cooling Water Pump",
        asset_type=AssetType.PUMP,
        status=AssetStatus.OPERATIONAL,
        criticality=Criticality.CRITICAL,
        location="Cooling Water Area",
    )
    database_session.add(asset)
    database_session.flush()

    work_order = WorkOrder(
        work_order_number="WO-OBSERVE-001",
        asset_id=asset.id,
        title="Inspect elevated P-101 vibration",
        description="Inspect bearings and coupling alignment.",
        priority=WorkOrderPriority.HIGH,
        status=WorkOrderStatus.PENDING_APPROVAL,
        revision=1,
        proposed_by="maintenance-agent",
        idempotency_key="observe-run-001",
    )
    database_session.add(work_order)
    database_session.flush()

    approval = Approval(
        work_order_id=work_order.id,
        request_version=1,
        decision=decision,
        approval_scope=approval_scope,
        requested_by="maintenance-agent",
        decided_by=("maintenance-supervisor" if decision == ApprovalDecision.APPROVED else None),
        decided_at=(COMPLETED_AT if decision == ApprovalDecision.APPROVED else None),
        decision_reason=(
            "Inspection plan reviewed and approved."
            if decision == ApprovalDecision.APPROVED
            else None
        ),
    )
    database_session.add(approval)
    database_session.commit()

    return approval


def test_record_agent_step_persists_validated_step(
    database_session: Session,
) -> None:
    step = record_agent_step(
        database_session,
        create_step_input(),
    )

    persisted_step = database_session.get(
        AgentStep,
        step.id,
    )

    assert persisted_step is not None
    assert persisted_step.run_id == "run-observe-001"
    assert persisted_step.step_number == 1
    assert persisted_step.status == AgentStepStatus.COMPLETED
    assert persisted_step.duration_ms == 20


def test_record_agent_step_rejects_unknown_run(
    database_session: Session,
) -> None:
    with pytest.raises(
        ObservabilityReferenceError,
        match="was not found",
    ):
        record_agent_step(
            database_session,
            create_step_input(
                run_id="missing-run",
            ),
        )


def test_record_agent_step_rejects_duplicate_number(
    database_session: Session,
) -> None:
    record_agent_step(
        database_session,
        create_step_input(),
    )

    with pytest.raises(
        ObservabilityConflictError,
        match="already contains step",
    ):
        record_agent_step(
            database_session,
            create_step_input(),
        )

    step_count = database_session.scalar(select(func.count()).select_from(AgentStep))

    assert step_count == 1


def test_record_tool_call_persists_validated_result(
    database_session: Session,
) -> None:
    step = record_agent_step(
        database_session,
        create_step_input(),
    )

    tool_call = record_tool_call(
        database_session,
        create_tool_call_input(
            step_id=step.id,
        ),
    )

    persisted_tool_call = database_session.get(
        ToolCall,
        tool_call.id,
    )

    assert persisted_tool_call is not None
    assert persisted_tool_call.run_id == "run-observe-001"
    assert persisted_tool_call.step_id == step.id
    assert persisted_tool_call.tool_name == "get_asset_details"
    assert persisted_tool_call.status == ToolCallStatus.SUCCEEDED
    assert persisted_tool_call.result_json == {
        "asset_code": "P-101",
        "status": "operational",
    }


def test_record_tool_call_rejects_unknown_run(
    database_session: Session,
) -> None:
    with pytest.raises(
        ObservabilityReferenceError,
        match="was not found",
    ):
        record_tool_call(
            database_session,
            create_tool_call_input(
                run_id="missing-run",
            ),
        )


def test_record_tool_call_rejects_step_from_another_run(
    database_session: Session,
) -> None:
    other_run_step = record_agent_step(
        database_session,
        create_step_input(
            run_id="run-observe-002",
        ),
    )

    with pytest.raises(
        ObservabilityReferenceError,
        match="does not belong",
    ):
        record_tool_call(
            database_session,
            create_tool_call_input(
                step_id=other_run_step.id,
            ),
        )


def test_blocked_state_changing_tool_call_is_audited(
    database_session: Session,
) -> None:
    record = ToolCallRecordInput(
        run_id="run-observe-001",
        tool_name="execute_work_order",
        arguments_json={"work_order_id": 1},
        status=ToolCallStatus.BLOCKED,
        is_state_changing=True,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        latency_ms=20,
        error_message="Human approval was not provided.",
    )

    tool_call = record_tool_call(
        database_session,
        record,
    )

    assert tool_call.status == ToolCallStatus.BLOCKED
    assert tool_call.is_state_changing is True
    assert tool_call.approval_id is None


def test_approved_state_changing_tool_call_is_persisted(
    database_session: Session,
) -> None:
    approval = create_approval(
        database_session,
    )
    record = ToolCallRecordInput(
        run_id="run-observe-001",
        approval_id=approval.id,
        tool_name="execute_work_order",
        arguments_json={"work_order_id": approval.work_order_id},
        result_json={"accepted": True},
        status=ToolCallStatus.SUCCEEDED,
        is_state_changing=True,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        latency_ms=20,
    )

    tool_call = record_tool_call(
        database_session,
        record,
    )

    assert tool_call.status == ToolCallStatus.SUCCEEDED
    assert tool_call.is_state_changing is True
    assert tool_call.approval_id == approval.id


def test_state_changing_tool_call_rejects_pending_approval(
    database_session: Session,
) -> None:
    approval = create_approval(
        database_session,
        decision=ApprovalDecision.PENDING,
    )
    record = ToolCallRecordInput(
        run_id="run-observe-001",
        approval_id=approval.id,
        tool_name="execute_work_order",
        arguments_json={"work_order_id": approval.work_order_id},
        result_json={"accepted": True},
        status=ToolCallStatus.SUCCEEDED,
        is_state_changing=True,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        latency_ms=20,
    )

    with pytest.raises(
        ObservabilityApprovalError,
        match="has not been approved",
    ):
        record_tool_call(
            database_session,
            record,
        )


def test_state_changing_tool_call_rejects_wrong_approval_scope(
    database_session: Session,
) -> None:
    approval = create_approval(
        database_session,
        approval_scope="review_only",
    )
    record = ToolCallRecordInput(
        run_id="run-observe-001",
        approval_id=approval.id,
        tool_name="execute_work_order",
        arguments_json={"work_order_id": approval.work_order_id},
        result_json={"accepted": True},
        status=ToolCallStatus.SUCCEEDED,
        is_state_changing=True,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        latency_ms=20,
    )

    with pytest.raises(
        ObservabilityApprovalError,
        match="does not permit work-order execution",
    ):
        record_tool_call(
            database_session,
            record,
        )


def test_record_model_usage_accumulates_run_metrics(
    database_session: Session,
) -> None:
    first_result = record_model_usage(
        database_session,
        ModelUsageRecordInput(
            run_id="run-observe-001",
            model_calls=1,
            prompt_tokens=100,
            completion_tokens=25,
            total_tokens=125,
        ),
    )
    second_result = record_model_usage(
        database_session,
        ModelUsageRecordInput(
            run_id="run-observe-001",
            model_calls=1,
            prompt_tokens=80,
            completion_tokens=20,
            total_tokens=100,
        ),
    )

    assert first_result.id == second_result.id
    assert second_result.model_calls == 2
    assert second_result.prompt_tokens == 180
    assert second_result.completion_tokens == 45
    assert second_result.total_tokens == 225
    assert second_result.estimated_cost_usd == 0.0


def test_record_model_usage_counts_call_without_metadata(
    database_session: Session,
) -> None:
    run = record_model_usage(
        database_session,
        ModelUsageRecordInput(
            run_id="run-observe-001",
        ),
    )

    assert run.model_calls == 1
    assert run.prompt_tokens == 0
    assert run.completion_tokens == 0
    assert run.total_tokens == 0
    assert run.estimated_cost_usd == 0.0


def test_record_model_usage_rejects_unknown_run(
    database_session: Session,
) -> None:
    with pytest.raises(
        ObservabilityReferenceError,
        match="was not found",
    ):
        record_model_usage(
            database_session,
            ModelUsageRecordInput(
                run_id="missing-run",
            ),
        )
