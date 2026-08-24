from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.agent.runtime import AgentRuntime
from app.main import create_app
from app.models.enums import AgentRunStatus
from app.schemas.agent_api import AgentRunResponse


def create_completed_response() -> AgentRunResponse:
    return AgentRunResponse(
        run_id="lazy-runtime-run",
        thread_id="lazy-runtime-thread",
        status=AgentRunStatus.COMPLETED,
        started_at=datetime(
            2026,
            8,
            25,
            10,
            0,
            tzinfo=UTC,
        ),
        completed_at=datetime(
            2026,
            8,
            25,
            10,
            1,
            tzinfo=UTC,
        ),
        final_response="Investigation completed.",
    )


def test_health_does_not_initialize_agent_runtime() -> None:
    runtime_factory = Mock()
    application = create_app(
        runtime_factory=runtime_factory,
    )

    with TestClient(application) as client:
        response = client.get("/health")

    assert response.status_code == 200
    runtime_factory.assert_not_called()


def test_agent_runtime_initializes_once_and_closes_on_shutdown(
    monkeypatch,
) -> None:
    graph = Mock()
    runtime_state = {
        "entered": 0,
        "closed": 0,
    }

    @contextmanager
    def runtime_context() -> Iterator[AgentRuntime]:
        runtime_state["entered"] += 1

        try:
            yield AgentRuntime(
                graph=graph,
            )
        finally:
            runtime_state["closed"] += 1

    runtime_factory = Mock(
        side_effect=runtime_context,
    )
    service = Mock(
        return_value=create_completed_response(),
    )
    monkeypatch.setattr(
        "app.api.routes.agent.get_agent_run",
        service,
    )
    application = create_app(
        runtime_factory=runtime_factory,
    )

    with TestClient(application) as client:
        first_response = client.get(
            "/agent/runs/lazy-runtime-run",
        )
        second_response = client.get(
            "/agent/runs/lazy-runtime-run",
        )

        assert first_response.status_code == 200
        assert second_response.status_code == 200
        assert runtime_state["entered"] == 1
        assert runtime_state["closed"] == 0

    runtime_factory.assert_called_once_with()
    assert runtime_state["closed"] == 1
    assert service.call_count == 2
    assert application.state.agent_graph is None
    assert application.state.agent_runtime_context is None


def test_agent_runtime_initialization_failure_returns_503(
    monkeypatch,
) -> None:
    service = Mock(
        return_value=create_completed_response(),
    )
    monkeypatch.setattr(
        "app.api.routes.agent.get_agent_run",
        service,
    )

    @contextmanager
    def failing_runtime_context() -> Iterator[AgentRuntime]:
        raise RuntimeError("Synthetic runtime initialization failure.")
        yield

    runtime_factory = Mock(
        side_effect=failing_runtime_context,
    )
    application = create_app(
        runtime_factory=runtime_factory,
    )

    with TestClient(application) as client:
        health_response = client.get("/health")
        agent_response = client.get(
            "/agent/runs/lazy-runtime-run",
        )

    assert health_response.status_code == 200
    assert agent_response.status_code == 503
    assert agent_response.json() == {"detail": "The agent workflow runtime is not available."}
    runtime_factory.assert_called_once_with()
    service.assert_not_called()
