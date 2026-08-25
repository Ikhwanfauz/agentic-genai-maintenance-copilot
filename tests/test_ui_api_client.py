import json
from collections.abc import Callable

import httpx2
import pytest

from app.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
)
from app.schemas.agent_api import (
    AgentApprovalDecisionRequest,
    AgentInvestigationStartRequest,
)
from app.ui import (
    MaintenanceApiClient,
    MaintenanceApiConnectionError,
    MaintenanceApiContractError,
    MaintenanceApiResponseError,
)

MockHandler = Callable[[httpx2.Request], httpx2.Response]


def completed_run_payload(
    *,
    run_id: str = "run-ui-001",
) -> dict[str, object]:
    return {
        "run_id": run_id,
        "thread_id": "thread-ui-001",
        "status": "completed",
        "started_at": "2026-08-26T10:00:00Z",
        "completed_at": "2026-08-26T10:01:00Z",
        "final_response": "Investigation completed.",
    }


def create_client(
    handler: MockHandler,
) -> MaintenanceApiClient:
    return MaintenanceApiClient(
        "http://maintenance-api.test",
        transport=httpx2.MockTransport(handler),
    )


def test_start_investigation_sends_typed_request() -> None:
    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        assert request.method == "POST"
        assert request.url.path == "/agent/investigations"

        request_payload = json.loads(request.content)

        assert request_payload == {
            "user_query": "Investigate unusual pump vibration.",
            "asset_code": "P-101",
            "max_iterations": 6,
        }

        return httpx2.Response(
            status_code=201,
            json=completed_run_payload(),
        )

    investigation_request = AgentInvestigationStartRequest(
        user_query="Investigate unusual pump vibration.",
        asset_code="P-101",
    )

    with create_client(handler) as client:
        response = client.start_investigation(
            investigation_request,
        )

    assert response.run_id == "run-ui-001"
    assert response.status == AgentRunStatus.COMPLETED
    assert response.final_response == "Investigation completed."


def test_get_run_uses_requested_run_id() -> None:
    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        assert request.method == "GET"
        assert request.url.path == "/agent/runs/run-ui-002"

        return httpx2.Response(
            status_code=200,
            json=completed_run_payload(
                run_id="run-ui-002",
            ),
        )

    with create_client(handler) as client:
        response = client.get_run("  run-ui-002  ")

    assert response.run_id == "run-ui-002"
    assert response.status == AgentRunStatus.COMPLETED


def test_submit_approval_sends_human_decision() -> None:
    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        assert request.method == "POST"
        assert request.url.path == ("/agent/runs/run-ui-approval/approval")

        request_payload = json.loads(request.content)

        assert request_payload == {
            "request_version": 1,
            "decision": "rejected",
            "decided_by": "Maintenance Supervisor",
            "decision_reason": ("More vibration evidence is required."),
            "decision_source": "human",
            "approval_scope": "execute_work_order",
        }

        return httpx2.Response(
            status_code=200,
            json=completed_run_payload(
                run_id="run-ui-approval",
            ),
        )

    approval_request = AgentApprovalDecisionRequest(
        request_version=1,
        decision=ApprovalDecision.REJECTED,
        decided_by="Maintenance Supervisor",
        decision_reason="More vibration evidence is required.",
    )

    with create_client(handler) as client:
        response = client.submit_approval(
            "run-ui-approval",
            approval_request,
        )

    assert response.run_id == "run-ui-approval"


def test_api_error_preserves_status_and_detail() -> None:
    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(
            status_code=404,
            json={
                "detail": "Agent run run-missing was not found.",
            },
        )

    with create_client(handler) as client:
        with pytest.raises(
            MaintenanceApiResponseError,
            match="Agent run run-missing was not found",
        ) as error_info:
            client.get_run("run-missing")

    assert error_info.value.status_code == 404
    assert error_info.value.detail == ("Agent run run-missing was not found.")


def test_non_json_api_error_uses_safe_fallback() -> None:
    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(
            status_code=503,
            content=b"Service unavailable",
        )

    with create_client(handler) as client:
        with pytest.raises(
            MaintenanceApiResponseError,
        ) as error_info:
            client.get_run("run-unavailable")

    assert error_info.value.status_code == 503
    assert error_info.value.detail == ("Request failed with HTTP 503.")


def test_connection_failure_is_translated() -> None:
    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        raise httpx2.ConnectError(
            "Connection refused.",
            request=request,
        )

    with create_client(handler) as client:
        with pytest.raises(
            MaintenanceApiConnectionError,
            match="could not be reached",
        ):
            client.get_run("run-ui-001")


def test_invalid_json_response_is_rejected() -> None:
    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(
            status_code=200,
            content=b"not-json",
        )

    with create_client(handler) as client:
        with pytest.raises(
            MaintenanceApiContractError,
            match="returned invalid JSON",
        ):
            client.get_run("run-ui-001")


def test_invalid_agent_run_contract_is_rejected() -> None:
    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        return httpx2.Response(
            status_code=200,
            json={
                "run_id": "run-ui-001",
                "thread_id": "thread-ui-001",
                "status": "completed",
                "started_at": "2026-08-26T10:00:00Z",
            },
        )

    with create_client(handler) as client:
        with pytest.raises(
            MaintenanceApiContractError,
            match="did not match AgentRunResponse",
        ):
            client.get_run("run-ui-001")


@pytest.mark.parametrize(
    "invalid_run_id",
    [
        "",
        "   ",
        "run/unsafe",
        r"run\unsafe",
    ],
)
def test_run_id_rejects_empty_or_unsafe_paths(
    invalid_run_id: str,
) -> None:
    def handler(
        request: httpx2.Request,
    ) -> httpx2.Response:
        raise AssertionError("HTTP request must not be sent.")

    with create_client(handler) as client:
        with pytest.raises(ValueError):
            client.get_run(invalid_run_id)


@pytest.mark.parametrize(
    "invalid_base_url",
    [
        "",
        "localhost:8000",
        "ftp://maintenance-api.test",
    ],
)
def test_client_rejects_invalid_base_url(
    invalid_base_url: str,
) -> None:
    with pytest.raises(
        ValueError,
        match="valid HTTP or HTTPS URL",
    ):
        MaintenanceApiClient(invalid_base_url)


def test_client_rejects_non_positive_timeout() -> None:
    with pytest.raises(
        ValueError,
        match="greater than zero",
    ):
        MaintenanceApiClient(
            "http://maintenance-api.test",
            timeout_seconds=0,
        )
