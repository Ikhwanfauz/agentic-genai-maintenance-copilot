from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import create_database_engine
from app.models.agent_log import AgentRun
from app.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
    WorkOrderPriority,
)
from app.schemas.actions import WorkOrderProposalOutput
from app.schemas.agent_api import AgentInvestigationStartRequest
from app.schemas.hitl import WorkOrderApprovalInterrupt
from app.services.agent_workflows import start_agent_investigation
from app.services.exceptions import AgentWorkflowExecutionError


class StubAgentGraph:
    def __init__(
        self,
        result: Mapping[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.received_input: object | None = None
        self.received_config: dict[str, object] | None = None

    def invoke(
        self,
        input: object,
        *,
        config: dict[str, object],
    ) -> Mapping[str, object]:
        self.received_input = input
        self.received_config = config

        if self.error is not None:
            raise self.error

        if self.result is None:
            raise AssertionError("Stub graph requires a result or error.")

        return self.result


@pytest.fixture
def database_session(
    tmp_path: Path,
) -> Iterator[Session]:
    database_path = tmp_path / "agent_workflow_service.sqlite"
    engine = create_database_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )

    with factory() as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_start_investigation_persists_completed_run(
    database_session: Session,
) -> None:
    graph = StubAgentGraph(
        result={
            "status": "completed",
            "diagnosis": None,
            "work_order_proposal": None,
            "approval_interrupt": None,
            "approval_decision": None,
            "error": None,
        }
    )
    clock_values = iter(
        [
            datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
            datetime(2026, 8, 24, 10, 0, 1, tzinfo=UTC),
        ]
    )

    response = start_agent_investigation(
        database_session,
        graph,
        AgentInvestigationStartRequest(
            user_query="Investigate reported P-101 vibration.",
            asset_code="P-101",
            thread_id="thread-service-001",
        ),
        workflow_clock=lambda: next(clock_values),
        run_id_factory=lambda: "run-service-001",
        model_provider="fake",
        model_name="fake-maintenance-model",
    )

    stored_run = database_session.get(
        AgentRun,
        "run-service-001",
    )

    assert stored_run is not None
    assert stored_run.status == AgentRunStatus.COMPLETED
    assert stored_run.thread_id == "thread-service-001"
    assert stored_run.user_query == "Investigate reported P-101 vibration."
    assert stored_run.model_provider == "fake"
    assert stored_run.model_name == "fake-maintenance-model"
    assert stored_run.duration_ms == 1000

    assert response.run_id == "run-service-001"
    assert response.thread_id == "thread-service-001"
    assert response.status == AgentRunStatus.COMPLETED
    assert response.completed_at is not None

    assert isinstance(graph.received_input, dict)
    assert graph.received_input["run_id"] == "run-service-001"
    assert graph.received_input["thread_id"] == "thread-service-001"
    assert graph.received_input["asset_code"] == "P-101"
    assert graph.received_config == {
        "configurable": {
            "thread_id": "thread-service-001",
        }
    }


def test_start_investigation_uses_run_id_as_default_thread(
    database_session: Session,
) -> None:
    graph = StubAgentGraph(
        result={
            "status": "completed",
            "diagnosis": None,
            "work_order_proposal": None,
            "approval_interrupt": None,
            "approval_decision": None,
            "error": None,
        }
    )
    clock_values = iter(
        [
            datetime(2026, 8, 24, 11, 0, tzinfo=UTC),
            datetime(2026, 8, 24, 11, 0, 1, tzinfo=UTC),
        ]
    )

    response = start_agent_investigation(
        database_session,
        graph,
        AgentInvestigationStartRequest(
            user_query="Investigate the equipment condition.",
        ),
        workflow_clock=lambda: next(clock_values),
        run_id_factory=lambda: "run-generated-thread",
    )

    assert response.run_id == "run-generated-thread"
    assert response.thread_id == "run-generated-thread"


def test_start_investigation_persists_approval_pause(
    database_session: Session,
) -> None:
    proposal = WorkOrderProposalOutput(
        asset_code="P-101",
        work_order_id=1,
        work_order_number="WO-SERVICE-001",
        title="P-101: Inspect pump bearings",
        description="Inspect pump bearings after grounded vibration diagnosis.",
        priority=WorkOrderPriority.HIGH,
        revision=1,
        proposed_by="maintenance-agent",
        idempotency_key="agent-proposal:service-001",
        approval_id=1,
        approval_decision=ApprovalDecision.PENDING,
        request_version=1,
        approval_scope="execute_work_order",
        created_new=True,
    )
    approval_interrupt = WorkOrderApprovalInterrupt(
        run_id="run-waiting-001",
        thread_id="thread-waiting-001",
        proposal=proposal,
    )
    graph = StubAgentGraph(
        result={
            "status": "waiting_for_approval",
            "diagnosis": None,
            "work_order_proposal": proposal,
            "approval_interrupt": approval_interrupt,
            "approval_decision": None,
            "error": None,
        }
    )

    response = start_agent_investigation(
        database_session,
        graph,
        AgentInvestigationStartRequest(
            user_query="Investigate and propose controlled inspection.",
            asset_code="P-101",
            thread_id="thread-waiting-001",
        ),
        workflow_clock=lambda: datetime(
            2026,
            8,
            24,
            12,
            0,
            tzinfo=UTC,
        ),
        run_id_factory=lambda: "run-waiting-001",
    )

    stored_run = database_session.get(
        AgentRun,
        "run-waiting-001",
    )

    assert stored_run is not None
    assert stored_run.status == AgentRunStatus.WAITING_FOR_APPROVAL
    assert stored_run.completed_at is None
    assert stored_run.duration_ms is None

    assert response.status == AgentRunStatus.WAITING_FOR_APPROVAL
    assert response.work_order_proposal == proposal
    assert response.approval_interrupt == approval_interrupt
    assert response.completed_at is None


def test_start_investigation_records_graph_failure(
    database_session: Session,
) -> None:
    graph = StubAgentGraph(
        error=RuntimeError("Synthetic graph failure."),
    )
    clock_values = iter(
        [
            datetime(2026, 8, 24, 13, 0, tzinfo=UTC),
            datetime(2026, 8, 24, 13, 0, 2, tzinfo=UTC),
        ]
    )

    with pytest.raises(
        AgentWorkflowExecutionError,
        match="failed during workflow execution",
    ):
        start_agent_investigation(
            database_session,
            graph,
            AgentInvestigationStartRequest(
                user_query="Investigate P-101.",
                asset_code="P-101",
            ),
            workflow_clock=lambda: next(clock_values),
            run_id_factory=lambda: "run-failed-001",
        )

    stored_run = database_session.get(
        AgentRun,
        "run-failed-001",
    )

    assert stored_run is not None
    assert stored_run.status == AgentRunStatus.FAILED
    assert stored_run.completed_at is not None
    assert stored_run.duration_ms == 2000
    assert stored_run.error_type == "RuntimeError"
    assert stored_run.error_message == "Synthetic graph failure."
