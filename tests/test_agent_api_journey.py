from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi.testclient import TestClient
from langgraph.types import Command
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.runtime import AgentRuntime
from app.api.routes.agent import get_db
from app.db.base import Base
from app.db.session import create_database_engine
from app.main import create_app
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
from app.schemas.actions import WorkOrderProposalOutput
from app.schemas.hitl import (
    WorkOrderApprovalInterrupt,
    WorkOrderApprovalResume,
)


@dataclass
class FakeAgentSnapshot:
    values: Mapping[str, object]


class FakeApiJourneyGraph:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
    ) -> None:
        self.session_factory = session_factory
        self.snapshot_values: dict[str, object] = {}
        self.investigation_invocations = 0
        self.resume_invocations = 0

    def invoke(
        self,
        input: object,
        *,
        config: dict[str, object],
    ) -> Mapping[str, object]:
        if isinstance(input, Command):
            return self._resume(
                input,
                config,
            )

        if not isinstance(input, dict):
            raise TypeError("The fake investigation graph requires typed state.")

        return self._start(
            input,
            config,
        )

    def get_state(
        self,
        config: dict[str, object],
    ) -> FakeAgentSnapshot:
        expected_config = {
            "configurable": {
                "thread_id": self.snapshot_values.get("thread_id"),
            }
        }

        if config != expected_config:
            raise ValueError("Status request used the wrong graph thread.")

        return FakeAgentSnapshot(
            values=self.snapshot_values,
        )

    def _start(
        self,
        state: dict[str, object],
        config: dict[str, object],
    ) -> Mapping[str, object]:
        self.investigation_invocations += 1

        run_id = str(state["run_id"])
        thread_id = str(state["thread_id"])

        if config != {
            "configurable": {
                "thread_id": thread_id,
            }
        }:
            raise ValueError("Investigation used the wrong graph thread.")

        with self.session_factory() as database_session:
            asset = database_session.scalar(select(Asset).where(Asset.asset_code == "P-101"))

            if asset is None:
                raise RuntimeError("The API journey requires seeded P-101.")

            work_order = WorkOrder(
                work_order_number="WO-API-E2E-001",
                asset_id=asset.id,
                title="P-101: Inspect pump coupling",
                description=("Inspect pump coupling after a grounded vibration investigation."),
                priority=WorkOrderPriority.HIGH,
                status=WorkOrderStatus.PENDING_APPROVAL,
                revision=1,
                proposed_by="maintenance-agent",
                idempotency_key=(f"api-e2e-proposal:{run_id}"),
            )
            database_session.add(work_order)
            database_session.flush()

            approval = Approval(
                work_order_id=work_order.id,
                request_version=1,
                decision=ApprovalDecision.PENDING,
                approval_scope="execute_work_order",
                requested_by="maintenance-agent",
            )
            database_session.add(approval)
            database_session.commit()

            proposal = WorkOrderProposalOutput(
                asset_code="P-101",
                work_order_id=work_order.id,
                work_order_number=(work_order.work_order_number),
                title=work_order.title,
                description=work_order.description,
                priority=work_order.priority,
                revision=work_order.revision,
                proposed_by=work_order.proposed_by,
                idempotency_key=(work_order.idempotency_key),
                approval_id=approval.id,
                approval_decision=(ApprovalDecision.PENDING),
                request_version=(approval.request_version),
                approval_scope=(approval.approval_scope),
                created_new=True,
            )

        approval_interrupt = WorkOrderApprovalInterrupt(
            run_id=run_id,
            thread_id=thread_id,
            proposal=proposal,
        )
        self.snapshot_values = {
            "run_id": run_id,
            "thread_id": thread_id,
            "status": "waiting_for_approval",
            "diagnosis": None,
            "work_order_proposal": proposal,
            "approval_interrupt": approval_interrupt,
            "approval_decision": None,
            "error": None,
        }

        return self.snapshot_values

    def _resume(
        self,
        command: Command,
        config: dict[str, object],
    ) -> Mapping[str, object]:
        self.resume_invocations += 1

        resume = WorkOrderApprovalResume.model_validate(command.resume)
        thread_id = str(self.snapshot_values["thread_id"])

        if config != {
            "configurable": {
                "thread_id": thread_id,
            }
        }:
            raise ValueError("Approval resume used the wrong graph thread.")

        self.snapshot_values = {
            **self.snapshot_values,
            "status": "completed",
            "approval_decision": resume.decision,
            "error": None,
        }

        return self.snapshot_values


def test_agent_rest_api_completes_human_approval_journey(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "api_journey.sqlite"
    engine = create_database_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        class_=Session,
        expire_on_commit=False,
    )

    with session_factory() as database_session:
        database_session.add(
            Asset(
                asset_code="P-101",
                name="Main Cooling Water Pump",
                asset_type=AssetType.PUMP,
                status=AssetStatus.OPERATIONAL,
                criticality=Criticality.CRITICAL,
                location="Cooling Water Area",
            )
        )
        database_session.commit()

    graph = FakeApiJourneyGraph(
        session_factory,
    )
    runtime_state = {
        "closed": False,
    }

    @contextmanager
    def runtime_factory() -> Iterator[AgentRuntime]:
        try:
            yield AgentRuntime(
                graph=graph,
            )
        finally:
            runtime_state["closed"] = True

    application = create_app(
        runtime_factory=runtime_factory,
    )

    def override_database_session() -> Iterator[Session]:
        with session_factory() as database_session:
            yield database_session

    application.dependency_overrides[get_db] = override_database_session

    try:
        with TestClient(application) as client:
            start_response = client.post(
                "/agent/investigations",
                json={
                    "user_query": (
                        "Investigate unusual P-101 vibration and propose a controlled inspection."
                    ),
                    "asset_code": "P-101",
                    "thread_id": "api-e2e-thread",
                },
            )

            assert start_response.status_code == 201
            started_run = start_response.json()
            run_id = started_run["run_id"]

            assert started_run["status"] == "waiting_for_approval"
            assert started_run["work_order_proposal"]["status"] == "pending_approval"
            assert (
                started_run["approval_interrupt"]["interrupt_type"]
                == "work_order_approval_required"
            )

            waiting_response = client.get(f"/agent/runs/{run_id}")

            assert waiting_response.status_code == 200
            assert waiting_response.json()["status"] == "waiting_for_approval"

            approval_response = client.post(
                f"/agent/runs/{run_id}/approval",
                json={
                    "request_version": 1,
                    "decision": "approved",
                    "decided_by": ("maintenance-supervisor"),
                    "decision_reason": ("Inspection plan reviewed and approved."),
                },
            )

            assert approval_response.status_code == 200
            approved_run = approval_response.json()

            assert approved_run["status"] == "completed"
            assert approved_run["approval_decision"]["decision"] == "approved"
            assert approved_run["approval_decision"]["work_order_status"] == "approved"

            final_status_response = client.get(f"/agent/runs/{run_id}")

            assert final_status_response.status_code == 200
            assert final_status_response.json()["status"] == "completed"
            assert final_status_response.json()["approval_decision"]["decision"] == "approved"

        assert runtime_state["closed"] is True
        assert graph.investigation_invocations == 1
        assert graph.resume_invocations == 1

        with session_factory() as database_session:
            agent_run = database_session.get(
                AgentRun,
                run_id,
            )
            work_order = database_session.scalar(select(WorkOrder))
            approval = database_session.scalar(select(Approval))

            assert agent_run is not None
            assert work_order is not None
            assert approval is not None

            assert agent_run.status == AgentRunStatus.COMPLETED
            assert work_order.status == WorkOrderStatus.APPROVED
            assert approval.decision == ApprovalDecision.APPROVED

            assert work_order.executed_at is None
            assert work_order.execution_summary is None
            assert approval.consumed_at is None

            assert database_session.scalar(select(func.count()).select_from(AgentRun)) == 1
            assert database_session.scalar(select(func.count()).select_from(WorkOrder)) == 1
            assert database_session.scalar(select(func.count()).select_from(Approval)) == 1
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()
