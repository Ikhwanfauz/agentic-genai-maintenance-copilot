from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.models.enums import (
    AgentStepStatus,
    AgentStepType,
    ToolCallStatus,
)
from app.schemas.observability import (
    AgentStepRecordInput,
    ToolCallRecordInput,
)

STARTED_AT = datetime(2026, 8, 25, 12, 0, tzinfo=UTC)
COMPLETED_AT = STARTED_AT + timedelta(milliseconds=25)


def test_completed_agent_step_contract_is_valid() -> None:
    record = AgentStepRecordInput(
        run_id="run-observe-001",
        step_number=1,
        step_type=AgentStepType.ROUTING,
        status=AgentStepStatus.COMPLETED,
        summary="  Initialized   maintenance investigation. ",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        duration_ms=25,
    )

    assert record.summary == "Initialized maintenance investigation."
    assert record.error_type is None
    assert record.error_message is None


def test_failed_agent_step_requires_error_details() -> None:
    with pytest.raises(
        ValidationError,
        match="requires error details",
    ):
        AgentStepRecordInput(
            run_id="run-observe-001",
            step_number=2,
            step_type=AgentStepType.EVIDENCE_SYNTHESIS,
            status=AgentStepStatus.FAILED,
            summary="Diagnosis synthesis failed.",
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
            duration_ms=25,
        )


def test_non_failed_agent_step_rejects_error_details() -> None:
    with pytest.raises(
        ValidationError,
        match="must not contain error details",
    ):
        AgentStepRecordInput(
            run_id="run-observe-001",
            step_number=2,
            step_type=AgentStepType.ROUTING,
            status=AgentStepStatus.COMPLETED,
            summary="Routing completed.",
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
            duration_ms=25,
            error_type="UnexpectedError",
            error_message="This must not be present.",
        )


def test_agent_step_rejects_invalid_timestamp_order() -> None:
    with pytest.raises(
        ValidationError,
        match="must not be earlier",
    ):
        AgentStepRecordInput(
            run_id="run-observe-001",
            step_number=1,
            step_type=AgentStepType.ROUTING,
            status=AgentStepStatus.COMPLETED,
            summary="Routing completed.",
            started_at=COMPLETED_AT,
            completed_at=STARTED_AT,
            duration_ms=25,
        )


def test_successful_read_only_tool_call_contract_is_valid() -> None:
    record = ToolCallRecordInput(
        run_id="run-observe-001",
        step_id=1,
        tool_name="get_asset_details",
        arguments_json={"asset_code": "P-101"},
        result_json={
            "asset_code": "P-101",
            "status": "operational",
        },
        status=ToolCallStatus.SUCCEEDED,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        latency_ms=25,
    )

    assert record.tool_name == "get_asset_details"
    assert record.is_state_changing is False
    assert record.approval_id is None


def test_successful_tool_call_requires_result() -> None:
    with pytest.raises(
        ValidationError,
        match="requires a result",
    ):
        ToolCallRecordInput(
            run_id="run-observe-001",
            tool_name="get_asset_details",
            arguments_json={"asset_code": "P-101"},
            status=ToolCallStatus.SUCCEEDED,
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
            latency_ms=25,
        )


def test_failed_tool_call_requires_error_details() -> None:
    with pytest.raises(
        ValidationError,
        match="requires error details",
    ):
        ToolCallRecordInput(
            run_id="run-observe-001",
            tool_name="get_asset_details",
            arguments_json={"asset_code": "UNKNOWN"},
            status=ToolCallStatus.FAILED,
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
            latency_ms=25,
        )


def test_state_changing_tool_call_requires_approval() -> None:
    with pytest.raises(
        ValidationError,
        match="non-blocked state-changing tool call requires an approval record",
    ):
        ToolCallRecordInput(
            run_id="run-observe-001",
            tool_name="execute_work_order",
            arguments_json={"work_order_id": 1},
            result_json={"accepted": True},
            status=ToolCallStatus.SUCCEEDED,
            is_state_changing=True,
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
            latency_ms=25,
        )


def test_blocked_tool_call_requires_reason() -> None:
    with pytest.raises(
        ValidationError,
        match="requires a reason",
    ):
        ToolCallRecordInput(
            run_id="run-observe-001",
            tool_name="execute_work_order",
            arguments_json={"work_order_id": 1},
            status=ToolCallStatus.BLOCKED,
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
            latency_ms=25,
        )


def test_blocked_state_changing_tool_call_can_be_audited_without_approval() -> None:
    record = ToolCallRecordInput(
        run_id="run-observe-001",
        tool_name="execute_work_order",
        arguments_json={"work_order_id": 1},
        status=ToolCallStatus.BLOCKED,
        is_state_changing=True,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        latency_ms=25,
        error_message="Human approval was not provided.",
    )

    assert record.status == ToolCallStatus.BLOCKED
    assert record.approval_id is None
