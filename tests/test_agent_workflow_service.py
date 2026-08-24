from collections.abc import Iterator, Mapping
from dataclasses import dataclass
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
from app.services.agent_workflows import (
    get_agent_run,
    start_agent_investigation,
)
from app.services.exceptions import (
    AgentRunNotFoundError,
    AgentWorkflowExecutionError,
    AgentWorkflowStateError,
)


@dataclass
class StubAgentSnapshot:
    values: Mapping[str, object]


class StubAgentGraph:
    def __init__(
        self,
        result: Mapping[str, object] | None = None,
        error: Exception | None = None,
        snapshot_values: Mapping[str, object] | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.snapshot_values = snapshot_values
        self.received_input: object | None = None
        self.received_config: dict[str, object] | None = None
        self.received_state_config: dict[str, object] | None = None

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

    def get_state(
        self,
        config: dict[str, object],
    ) -> StubAgentSnapshot:
        self.received_state_config = config

        return StubAgentSnapshot(
            values=self.snapshot_values or {},
        )


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


def test_get_agent_run_returns_persisted_completed_status(
    database_session: Session,
) -> None:
    started_at = datetime(2026, 8, 24, 14, 0, tzinfo=UTC)
    completed_at = datetime(2026, 8, 24, 14, 0, 1, tzinfo=UTC)
    run = AgentRun(
        id="run-status-completed",
        thread_id="thread-status-completed",
        user_query="Investigate completed status.",
        status=AgentRunStatus.COMPLETED,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=1000,
        final_response="Investigation completed.",
    )
    database_session.add(run)
    database_session.commit()
    database_session.expire_all()

    graph = StubAgentGraph(
        snapshot_values={
            "run_id": "run-status-completed",
            "thread_id": "thread-status-completed",
            "status": "completed",
            "diagnosis": None,
            "work_order_proposal": None,
            "approval_interrupt": None,
            "approval_decision": None,
            "error": None,
        }
    )

    response = get_agent_run(
        database_session,
        graph,
        " run-status-completed ",
    )

    assert response.run_id == "run-status-completed"
    assert response.thread_id == "thread-status-completed"
    assert response.status == AgentRunStatus.COMPLETED
    assert response.started_at.tzinfo is not None
    assert response.completed_at is not None
    assert response.completed_at.tzinfo is not None
    assert response.final_response == "Investigation completed."
    assert graph.received_state_config == {
        "configurable": {
            "thread_id": "thread-status-completed",
        }
    }


def test_get_agent_run_returns_waiting_approval_context(
    database_session: Session,
) -> None:
    proposal = WorkOrderProposalOutput(
        asset_code="P-101",
        work_order_id=2,
        work_order_number="WO-STATUS-002",
        title="P-101: Inspect pump coupling",
        description="Inspect pump coupling after grounded vibration diagnosis.",
        priority=WorkOrderPriority.HIGH,
        revision=1,
        proposed_by="maintenance-agent",
        idempotency_key="agent-proposal:status-002",
        approval_id=2,
        approval_decision=ApprovalDecision.PENDING,
        request_version=1,
        approval_scope="execute_work_order",
        created_new=True,
    )
    approval_interrupt = WorkOrderApprovalInterrupt(
        run_id="run-status-waiting",
        thread_id="thread-status-waiting",
        proposal=proposal,
    )
    run = AgentRun(
        id="run-status-waiting",
        thread_id="thread-status-waiting",
        user_query="Investigate and request controlled inspection.",
        status=AgentRunStatus.WAITING_FOR_APPROVAL,
        started_at=datetime(2026, 8, 24, 15, 0, tzinfo=UTC),
    )
    database_session.add(run)
    database_session.commit()

    graph = StubAgentGraph(
        snapshot_values={
            "run_id": "run-status-waiting",
            "thread_id": "thread-status-waiting",
            "status": "waiting_for_approval",
            "diagnosis": None,
            "work_order_proposal": proposal,
            "approval_interrupt": approval_interrupt,
            "approval_decision": None,
            "error": None,
        }
    )

    response = get_agent_run(
        database_session,
        graph,
        "run-status-waiting",
    )

    assert response.status == AgentRunStatus.WAITING_FOR_APPROVAL
    assert response.work_order_proposal == proposal
    assert response.approval_interrupt == approval_interrupt
    assert response.completed_at is None


def test_get_agent_run_rejects_unknown_run(
    database_session: Session,
) -> None:
    graph = StubAgentGraph()

    with pytest.raises(
        AgentRunNotFoundError,
        match="was not found",
    ):
        get_agent_run(
            database_session,
            graph,
            "missing-run",
        )

    assert graph.received_state_config is None


def test_get_agent_run_rejects_checkpoint_identity_mismatch(
    database_session: Session,
) -> None:
    run = AgentRun(
        id="run-status-secure",
        thread_id="thread-status-secure",
        user_query="Investigate checkpoint identity.",
        status=AgentRunStatus.COMPLETED,
        started_at=datetime(2026, 8, 24, 16, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 24, 16, 0, 1, tzinfo=UTC),
        duration_ms=1000,
    )
    database_session.add(run)
    database_session.commit()

    graph = StubAgentGraph(
        snapshot_values={
            "run_id": "wrong-run",
            "thread_id": "thread-status-secure",
            "status": "completed",
        }
    )

    with pytest.raises(
        AgentWorkflowStateError,
        match="run identity does not match",
    ):
        get_agent_run(
            database_session,
            graph,
            "run-status-secure",
        )


def test_get_failed_agent_run_survives_missing_checkpoint(
    database_session: Session,
) -> None:
    run = AgentRun(
        id="run-status-failed",
        thread_id="thread-status-failed",
        user_query="Investigate failed workflow status.",
        status=AgentRunStatus.FAILED,
        started_at=datetime(2026, 8, 24, 17, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 24, 17, 0, 2, tzinfo=UTC),
        duration_ms=2000,
        error_type="RuntimeError",
        error_message="Synthetic graph failure.",
    )
    database_session.add(run)
    database_session.commit()

    graph = StubAgentGraph(
        snapshot_values={},
    )

    response = get_agent_run(
        database_session,
        graph,
        "run-status-failed",
    )

    assert response.status == AgentRunStatus.FAILED
    assert response.error_type == "RuntimeError"
    assert response.error_message == "Synthetic graph failure."
    assert response.completed_at is not None
