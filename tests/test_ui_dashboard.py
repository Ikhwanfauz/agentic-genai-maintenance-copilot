from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError
from streamlit.testing.v1 import AppTest

import app.ui.dashboard as dashboard
from app.models.enums import AgentRunStatus
from app.schemas.agent_api import (
    AgentInvestigationStartRequest,
    AgentRunResponse,
)
from app.ui.dashboard import (
    ACTIVE_RUN_STATE_KEY,
    format_asset_option,
    load_active_run,
    start_investigation,
    store_active_run,
)


def completed_run() -> AgentRunResponse:
    return AgentRunResponse(
        run_id="run-dashboard-001",
        thread_id="thread-dashboard-001",
        status=AgentRunStatus.COMPLETED,
        started_at=datetime(
            2026,
            8,
            26,
            10,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            8,
            26,
            10,
            1,
            tzinfo=UTC,
        ),
        final_response="Investigation completed.",
    )


class FakeInvestigationClient:
    def __init__(
        self,
        response: AgentRunResponse,
    ) -> None:
        self.response = response
        self.received_request: AgentInvestigationStartRequest | None = None

    def start_investigation(
        self,
        request: AgentInvestigationStartRequest,
    ) -> AgentRunResponse:
        self.received_request = request
        return self.response


def test_start_investigation_builds_typed_request() -> None:
    client = FakeInvestigationClient(
        completed_run(),
    )

    response = start_investigation(
        client,
        user_query="  Investigate   unusual pump vibration. ",
        asset_code="p-101",
        max_iterations=5,
    )

    assert response.run_id == "run-dashboard-001"
    assert client.received_request is not None
    assert client.received_request.user_query == ("Investigate unusual pump vibration.")
    assert client.received_request.asset_code == "P-101"
    assert client.received_request.max_iterations == 5


def test_start_investigation_rejects_invalid_input_before_client_call() -> None:
    client = FakeInvestigationClient(
        completed_run(),
    )

    with pytest.raises(ValidationError):
        start_investigation(
            client,
            user_query="   ",
            asset_code="P-101",
            max_iterations=6,
        )

    assert client.received_request is None


def test_active_run_round_trip_uses_validated_session_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_state: dict[str, object] = {}
    monkeypatch.setattr(
        dashboard.st,
        "session_state",
        session_state,
    )

    store_active_run(
        completed_run(),
    )
    restored_run = load_active_run()

    assert ACTIVE_RUN_STATE_KEY in session_state
    assert restored_run is not None
    assert restored_run.run_id == "run-dashboard-001"
    assert restored_run.status == AgentRunStatus.COMPLETED
    assert restored_run.completed_at == datetime(
        2026,
        8,
        26,
        10,
        1,
        tzinfo=UTC,
    )


def test_invalid_session_run_is_removed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session_state: dict[str, object] = {
        ACTIVE_RUN_STATE_KEY: {
            "run_id": "run-invalid",
            "thread_id": "thread-invalid",
            "status": "completed",
            "started_at": "2026-08-26T10:00:00Z",
        }
    }
    monkeypatch.setattr(
        dashboard.st,
        "session_state",
        session_state,
    )

    restored_run = load_active_run()

    assert restored_run is None
    assert ACTIVE_RUN_STATE_KEY not in session_state


@pytest.mark.parametrize(
    ("asset_code", "expected_label"),
    [
        (
            None,
            "Let the agent identify the asset",
        ),
        (
            "P-101",
            "P-101",
        ),
        (
            "P-102",
            "P-102",
        ),
        (
            "P-201",
            "P-201",
        ),
        (
            "M-101",
            "M-101",
        ),
    ],
)
def test_asset_option_has_operator_label(
    asset_code: str | None,
    expected_label: str,
) -> None:
    assert format_asset_option(asset_code) == expected_label


def test_dashboard_shell_renders_without_api_call() -> None:
    application_path = Path(__file__).resolve().parents[1] / "streamlit_app.py"

    application = AppTest.from_file(
        application_path,
    ).run()

    assert not application.exception
    assert application.title[0].value == ("Agentic GenAI Maintenance Copilot")
    assert application.text_area[0].label == "Equipment issue"
    assert application.selectbox[0].label == "Asset"
    assert application.slider[0].label == ("Maximum agent iterations")
    assert application.slider[0].value == 6
    assert application.button[0].label == ("Start grounded investigation")
