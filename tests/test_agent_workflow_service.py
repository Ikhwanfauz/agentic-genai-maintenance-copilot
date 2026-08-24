from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.types import Command
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.session import create_database_engine
from app.models.agent_log import AgentRun
from app.models.approval import Approval
from app.models.asset import Asset
from app.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
    AssetStatus,
    AssetType,
    Criticality,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.models.work_order import WorkOrder
from app.schemas.actions import (
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)
from app.schemas.agent_api import (
    AgentApprovalDecisionRequest,
    AgentInvestigationStartRequest,
)
from app.schemas.hitl import WorkOrderApprovalInterrupt
from app.services.agent_workflows import (
    decide_agent_run_approval,
    get_agent_run,
    start_agent_investigation,
)
from app.services.exceptions import (
    AgentRunApprovalStateError,
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

        self.snapshot_values = self.result
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


def create_waiting_approval_context(
    database_session: Session,
    *,
    run_id: str,
    thread_id: str,
) -> tuple[
    WorkOrderProposalOutput,
    WorkOrderApprovalInterrupt,
]:
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
        id=101,
        work_order_number="WO-RESUME-101",
        asset_id=asset.id,
        title="P-101: Inspect pump coupling",
        description="Inspect pump coupling after grounded vibration diagnosis.",
        priority=WorkOrderPriority.HIGH,
        status=WorkOrderStatus.PENDING_APPROVAL,
        revision=1,
        proposed_by="maintenance-agent",
        idempotency_key=f"agent-proposal:{run_id}",
    )
    approval = Approval(
        id=201,
        work_order_id=101,
        request_version=1,
        decision=ApprovalDecision.PENDING,
        approval_scope="execute_work_order",
        requested_by="maintenance-agent",
    )
    run = AgentRun(
        id=run_id,
        thread_id=thread_id,
        user_query="Investigate and request controlled inspection.",
        status=AgentRunStatus.WAITING_FOR_APPROVAL,
        started_at=datetime(2026, 8, 24, 18, 0, tzinfo=UTC),
    )
    database_session.add_all(
        [
            work_order,
            approval,
            run,
        ]
    )
    database_session.commit()

    proposal = WorkOrderProposalOutput(
        asset_code="P-101",
        work_order_id=101,
        work_order_number="WO-RESUME-101",
        title=work_order.title,
        description=work_order.description,
        priority=work_order.priority,
        revision=work_order.revision,
        proposed_by=work_order.proposed_by,
        idempotency_key=work_order.idempotency_key,
        approval_id=201,
        approval_decision=ApprovalDecision.PENDING,
        request_version=1,
        approval_scope="execute_work_order",
        created_new=True,
    )
    approval_interrupt = WorkOrderApprovalInterrupt(
        run_id=run_id,
        thread_id=thread_id,
        proposal=proposal,
    )

    return proposal, approval_interrupt


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


@pytest.mark.parametrize(
    ("decision", "expected_status"),
    [
        (
            ApprovalDecision.APPROVED,
            WorkOrderStatus.APPROVED,
        ),
        (
            ApprovalDecision.REJECTED,
            WorkOrderStatus.REJECTED,
        ),
    ],
)
def test_decide_agent_run_approval_applies_and_resumes(
    database_session: Session,
    decision: ApprovalDecision,
    expected_status: WorkOrderStatus,
) -> None:
    run_id = f"run-resume-{decision.value}"
    thread_id = f"thread-resume-{decision.value}"
    proposal, approval_interrupt = create_waiting_approval_context(
        database_session,
        run_id=run_id,
        thread_id=thread_id,
    )
    decision_reason = (
        "Inspection plan reviewed and approved."
        if decision == ApprovalDecision.APPROVED
        else "Work scope requires further technical review."
    )
    decided_at = datetime(2026, 8, 24, 18, 1, tzinfo=UTC)
    expected_decision = WorkOrderApprovalDecisionOutput(
        work_order_id=101,
        work_order_number="WO-RESUME-101",
        approval_id=201,
        request_version=1,
        decision=decision,
        work_order_status=expected_status,
        decided_by="maintenance-supervisor",
        decided_at=decided_at,
        decision_reason=decision_reason,
        approval_scope="execute_work_order",
        decision_applied=True,
    )
    graph = StubAgentGraph(
        result={
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "completed",
            "diagnosis": None,
            "work_order_proposal": proposal,
            "approval_interrupt": approval_interrupt,
            "approval_decision": expected_decision,
            "error": None,
        },
        snapshot_values={
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "waiting_for_approval",
            "diagnosis": None,
            "work_order_proposal": proposal,
            "approval_interrupt": approval_interrupt,
            "approval_decision": None,
            "error": None,
        },
    )
    clock_values = iter(
        [
            decided_at,
            datetime(2026, 8, 24, 18, 2, tzinfo=UTC),
        ]
    )

    response = decide_agent_run_approval(
        database_session,
        graph,
        run_id,
        AgentApprovalDecisionRequest(
            request_version=1,
            decision=decision,
            decided_by="maintenance-supervisor",
            decision_reason=decision_reason,
        ),
        workflow_clock=lambda: next(clock_values),
    )

    work_order = database_session.get(WorkOrder, 101)
    approval = database_session.get(Approval, 201)
    stored_run = database_session.get(AgentRun, run_id)

    assert work_order is not None
    assert approval is not None
    assert stored_run is not None
    assert work_order.status == expected_status
    assert approval.decision == decision
    assert stored_run.status == AgentRunStatus.COMPLETED
    assert stored_run.completed_at is not None

    assert response.status == AgentRunStatus.COMPLETED
    assert response.approval_decision == expected_decision
    assert isinstance(graph.received_input, Command)
    assert work_order.executed_at is None
    assert work_order.execution_summary is None
    assert approval.consumed_at is None


def test_decide_agent_run_approval_rejects_non_waiting_run(
    database_session: Session,
) -> None:
    run = AgentRun(
        id="run-not-waiting",
        thread_id="thread-not-waiting",
        user_query="Completed investigation.",
        status=AgentRunStatus.COMPLETED,
        started_at=datetime(2026, 8, 24, 19, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 24, 19, 1, tzinfo=UTC),
        duration_ms=60000,
    )
    database_session.add(run)
    database_session.commit()

    with pytest.raises(
        AgentRunApprovalStateError,
        match="not waiting for approval",
    ):
        decide_agent_run_approval(
            database_session,
            StubAgentGraph(),
            "run-not-waiting",
            AgentApprovalDecisionRequest(
                request_version=1,
                decision=ApprovalDecision.APPROVED,
                decided_by="maintenance-supervisor",
                decision_reason="Inspection plan reviewed and approved.",
            ),
        )


def test_decide_agent_run_approval_rejects_tampered_approval_identity(
    database_session: Session,
) -> None:
    run_id = "run-tampered-approval"
    thread_id = "thread-tampered-approval"
    proposal, _approval_interrupt = create_waiting_approval_context(
        database_session,
        run_id=run_id,
        thread_id=thread_id,
    )
    tampered_proposal = proposal.model_copy(
        update={
            "approval_id": 999,
        }
    )
    tampered_interrupt = WorkOrderApprovalInterrupt(
        run_id=run_id,
        thread_id=thread_id,
        proposal=tampered_proposal,
    )
    graph = StubAgentGraph(
        snapshot_values={
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "waiting_for_approval",
            "diagnosis": None,
            "work_order_proposal": tampered_proposal,
            "approval_interrupt": tampered_interrupt,
            "approval_decision": None,
            "error": None,
        }
    )

    with pytest.raises(
        AgentWorkflowStateError,
        match="approval record does not exist",
    ):
        decide_agent_run_approval(
            database_session,
            graph,
            run_id,
            AgentApprovalDecisionRequest(
                request_version=1,
                decision=ApprovalDecision.APPROVED,
                decided_by="maintenance-supervisor",
                decision_reason="Inspection plan reviewed and approved.",
            ),
        )

    work_order = database_session.get(WorkOrder, 101)
    approval = database_session.get(Approval, 201)

    assert work_order is not None
    assert approval is not None
    assert work_order.status == WorkOrderStatus.PENDING_APPROVAL
    assert approval.decision == ApprovalDecision.PENDING


def test_decide_agent_run_approval_keeps_run_resumable_after_graph_failure(
    database_session: Session,
) -> None:
    run_id = "run-resume-failure"
    thread_id = "thread-resume-failure"
    proposal, approval_interrupt = create_waiting_approval_context(
        database_session,
        run_id=run_id,
        thread_id=thread_id,
    )
    graph = StubAgentGraph(
        error=RuntimeError("Synthetic resume failure."),
        snapshot_values={
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "waiting_for_approval",
            "diagnosis": None,
            "work_order_proposal": proposal,
            "approval_interrupt": approval_interrupt,
            "approval_decision": None,
            "error": None,
        },
    )

    with pytest.raises(
        AgentWorkflowExecutionError,
        match="failed during approval resume",
    ):
        decide_agent_run_approval(
            database_session,
            graph,
            run_id,
            AgentApprovalDecisionRequest(
                request_version=1,
                decision=ApprovalDecision.APPROVED,
                decided_by="maintenance-supervisor",
                decision_reason="Inspection plan reviewed and approved.",
            ),
            workflow_clock=lambda: datetime(
                2026,
                8,
                24,
                20,
                0,
                tzinfo=UTC,
            ),
        )

    work_order = database_session.get(WorkOrder, 101)
    approval = database_session.get(Approval, 201)
    stored_run = database_session.get(AgentRun, run_id)

    assert work_order is not None
    assert approval is not None
    assert stored_run is not None
    assert work_order.status == WorkOrderStatus.APPROVED
    assert approval.decision == ApprovalDecision.APPROVED
    assert stored_run.status == AgentRunStatus.WAITING_FOR_APPROVAL
    assert stored_run.completed_at is None
    assert stored_run.error_type == "RuntimeError"
    assert stored_run.error_message == "Synthetic resume failure."
