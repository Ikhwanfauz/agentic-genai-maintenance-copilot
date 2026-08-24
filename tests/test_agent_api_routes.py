from collections.abc import Iterator
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes.agent import router
from app.db.session import get_db
from app.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
)
from app.schemas.agent_api import (
    AgentApprovalDecisionRequest,
    AgentInvestigationStartRequest,
    AgentRunResponse,
)
from app.services.exceptions import (
    AgentRunApprovalStateError,
    AgentRunNotFoundError,
)


def create_completed_response(
    *,
    run_id: str = "api-run-001",
    thread_id: str = "api-thread-001",
) -> AgentRunResponse:
    return AgentRunResponse(
        run_id=run_id,
        thread_id=thread_id,
        status=AgentRunStatus.COMPLETED,
        started_at=datetime(
            2026,
            8,
            25,
            9,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            8,
            25,
            9,
            1,
            tzinfo=UTC,
        ),
        final_response="Investigation completed.",
    )


@pytest.fixture
def api_dependencies() -> tuple[
    FastAPI,
    Mock,
    Mock,
]:
    application = FastAPI()
    database_session = Mock(spec=Session)
    graph = Mock()
    application.state.agent_graph = graph
    application.include_router(router)

    def override_database_session() -> Iterator[Session]:
        yield database_session

    application.dependency_overrides[get_db] = override_database_session

    return (
        application,
        database_session,
        graph,
    )


def test_start_investigation_endpoint_returns_created_response(
    api_dependencies: tuple[FastAPI, Mock, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, database_session, graph = api_dependencies
    service = Mock(
        return_value=create_completed_response(),
    )
    monkeypatch.setattr(
        "app.api.routes.agent.start_agent_investigation",
        service,
    )

    with TestClient(application) as client:
        response = client.post(
            "/agent/investigations",
            json={
                "user_query": ("Investigate unusual P-101 vibration."),
                "asset_code": "p-101",
                "thread_id": "api-thread-001",
            },
        )

    assert response.status_code == 201
    assert response.json()["run_id"] == "api-run-001"
    assert response.json()["status"] == "completed"

    called_arguments = service.call_args.args
    assert called_arguments[0] is database_session
    assert called_arguments[1] is graph
    assert isinstance(
        called_arguments[2],
        AgentInvestigationStartRequest,
    )
    assert called_arguments[2].asset_code == "P-101"


def test_read_agent_run_endpoint_returns_status(
    api_dependencies: tuple[FastAPI, Mock, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, database_session, graph = api_dependencies
    service = Mock(
        return_value=create_completed_response(),
    )
    monkeypatch.setattr(
        "app.api.routes.agent.get_agent_run",
        service,
    )

    with TestClient(application) as client:
        response = client.get(
            "/agent/runs/api-run-001",
        )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    service.assert_called_once_with(
        database_session,
        graph,
        "api-run-001",
    )


def test_approval_endpoint_passes_typed_human_decision(
    api_dependencies: tuple[FastAPI, Mock, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, database_session, graph = api_dependencies
    service = Mock(
        return_value=create_completed_response(),
    )
    monkeypatch.setattr(
        "app.api.routes.agent.decide_agent_run_approval",
        service,
    )

    with TestClient(application) as client:
        response = client.post(
            "/agent/runs/api-run-001/approval",
            json={
                "request_version": 1,
                "decision": "approved",
                "decided_by": "maintenance-supervisor",
                "decision_reason": ("Inspection plan reviewed and approved."),
            },
        )

    assert response.status_code == 200

    called_arguments = service.call_args.args
    assert called_arguments[0] is database_session
    assert called_arguments[1] is graph
    assert called_arguments[2] == "api-run-001"
    assert isinstance(
        called_arguments[3],
        AgentApprovalDecisionRequest,
    )
    assert called_arguments[3].decision == ApprovalDecision.APPROVED


def test_read_agent_run_maps_missing_run_to_not_found(
    api_dependencies: tuple[FastAPI, Mock, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _database_session, _graph = api_dependencies
    service = Mock(
        side_effect=AgentRunNotFoundError("missing-run"),
    )
    monkeypatch.setattr(
        "app.api.routes.agent.get_agent_run",
        service,
    )

    with TestClient(application) as client:
        response = client.get(
            "/agent/runs/missing-run",
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Agent run 'missing-run' was not found."}


def test_approval_endpoint_maps_state_conflict(
    api_dependencies: tuple[FastAPI, Mock, Mock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application, _database_session, _graph = api_dependencies
    service = Mock(
        side_effect=AgentRunApprovalStateError("Agent run is not waiting for approval."),
    )
    monkeypatch.setattr(
        "app.api.routes.agent.decide_agent_run_approval",
        service,
    )

    with TestClient(application) as client:
        response = client.post(
            "/agent/runs/api-run-001/approval",
            json={
                "request_version": 1,
                "decision": "approved",
                "decided_by": "maintenance-supervisor",
                "decision_reason": ("Inspection plan reviewed and approved."),
            },
        )

    assert response.status_code == 409
    assert response.json() == {"detail": "Agent run is not waiting for approval."}


def test_agent_endpoint_requires_runtime_graph() -> None:
    application = FastAPI()
    database_session = Mock(spec=Session)
    application.include_router(router)

    def override_database_session() -> Iterator[Session]:
        yield database_session

    application.dependency_overrides[get_db] = override_database_session

    with TestClient(application) as client:
        response = client.get(
            "/agent/runs/api-run-001",
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "The agent workflow runtime is not available."}
