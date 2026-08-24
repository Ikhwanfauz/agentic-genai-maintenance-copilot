from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
)
from app.schemas.agent_api import (
    AgentApprovalDecisionRequest,
    AgentInvestigationStartRequest,
    AgentRunResponse,
)


def test_investigation_request_normalizes_input() -> None:
    request = AgentInvestigationStartRequest(
        user_query="  Investigate   unusual pump vibration.  ",
        asset_code=" p-101 ",
        thread_id=" maintenance-thread-001 ",
    )

    assert request.user_query == "Investigate unusual pump vibration."
    assert request.asset_code == "P-101"
    assert request.thread_id == "maintenance-thread-001"
    assert request.max_iterations == 6


def test_investigation_request_allows_application_generated_thread() -> None:
    request = AgentInvestigationStartRequest(
        user_query="Investigate the reported equipment condition.",
        asset_code=None,
    )

    assert request.asset_code is None
    assert request.thread_id is None


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("user_query", "   "),
        ("asset_code", "invalid"),
        ("thread_id", "   "),
        ("max_iterations", 0),
        ("max_iterations", 11),
    ],
)
def test_investigation_request_rejects_invalid_values(
    field_name: str,
    field_value: object,
) -> None:
    payload: dict[str, object] = {
        "user_query": "Investigate abnormal vibration.",
        "asset_code": "P-101",
    }
    payload[field_name] = field_value

    with pytest.raises(ValidationError):
        AgentInvestigationStartRequest.model_validate(payload)


def test_investigation_request_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        AgentInvestigationStartRequest.model_validate(
            {
                "user_query": "Investigate abnormal vibration.",
                "asset_code": "P-101",
                "execute_machine": True,
            }
        )


def test_approval_request_accepts_only_human_final_decision() -> None:
    request = AgentApprovalDecisionRequest(
        request_version=1,
        decision=ApprovalDecision.APPROVED,
        decided_by="  Maintenance Supervisor  ",
        decision_reason="  Inspection plan   reviewed and approved.  ",
    )

    assert request.decision == ApprovalDecision.APPROVED
    assert request.decided_by == "Maintenance Supervisor"
    assert request.decision_reason == "Inspection plan reviewed and approved."
    assert request.decision_source == "human"
    assert request.approval_scope == "execute_work_order"


@pytest.mark.parametrize(
    "decision",
    [
        ApprovalDecision.PENDING,
        ApprovalDecision.EXPIRED,
        ApprovalDecision.REVOKED,
    ],
)
def test_approval_request_rejects_non_final_decision(
    decision: ApprovalDecision,
) -> None:
    with pytest.raises(ValidationError):
        AgentApprovalDecisionRequest(
            request_version=1,
            decision=decision,
            decided_by="Maintenance Supervisor",
            decision_reason="This is not a permitted final human decision.",
        )


def test_completed_run_response_requires_completion_timestamp() -> None:
    with pytest.raises(
        ValidationError,
        match="terminal agent run requires",
    ):
        AgentRunResponse(
            run_id="run-001",
            thread_id="thread-001",
            status=AgentRunStatus.COMPLETED,
            started_at=datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
        )


def test_completed_run_response_accepts_terminal_lifecycle() -> None:
    started_at = datetime(2026, 8, 24, 10, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 24, 10, 1, tzinfo=UTC)

    response = AgentRunResponse(
        run_id="run-001",
        thread_id="thread-001",
        status=AgentRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        final_response="Investigation completed.",
    )

    assert response.status == AgentRunStatus.COMPLETED
    assert response.started_at == started_at
    assert response.completed_at == completed_at


def test_waiting_run_response_requires_approval_context() -> None:
    with pytest.raises(
        ValidationError,
        match="requires an approval interrupt",
    ):
        AgentRunResponse(
            run_id="run-001",
            thread_id="thread-001",
            status=AgentRunStatus.WAITING_FOR_APPROVAL,
            started_at=datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
        )
