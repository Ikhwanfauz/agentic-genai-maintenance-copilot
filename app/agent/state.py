from enum import StrEnum
from operator import add
from typing import Annotated
from uuid import uuid4

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.schemas.actions import (
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)
from app.schemas.diagnosis import MaintenanceDiagnosis
from app.schemas.evidence import CollectedEvidence
from app.schemas.hitl import WorkOrderApprovalInterrupt
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    EvidenceCoverage,
)


class AgentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    AWAITING_TOOL = "awaiting_tool"
    COMPLETED = "completed"
    LIMIT_REACHED = "limit_reached"
    FAILED = "failed"
    REJECTED = "rejected"
    WAITING_FOR_APPROVAL = "waiting_for_approval"


class AgentRoute(StrEnum):
    INVESTIGATE = "investigate"
    TOOLS = "tools"
    SYNTHESIZE = "synthesize"
    END = "end"
    APPROVAL = "approval"


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str
    thread_id: str
    user_query: str
    asset_code: str | None
    iteration_count: int
    max_iterations: int
    status: AgentStatus
    route: AgentRoute | None
    visited_nodes: Annotated[list[str], add]
    error: str | None
    evidence_ledger: Annotated[list[CollectedEvidence], add]
    evidence_coverage: EvidenceCoverage | None
    grounding_result: DiagnosisGroundingResult | None
    diagnosis: MaintenanceDiagnosis | None
    work_order_proposal: WorkOrderProposalOutput | None
    approval_interrupt: WorkOrderApprovalInterrupt | None
    approval_decision: WorkOrderApprovalDecisionOutput | None


def create_initial_state(
    user_query: str,
    asset_code: str | None = None,
    *,
    max_iterations: int = 6,
    run_id: str | None = None,
    thread_id: str | None = None,
) -> AgentState:
    if not 1 <= max_iterations <= 10:
        raise ValueError("max_iterations must be between 1 and 10.")

    normalized_query = user_query.strip()
    normalized_asset_code = asset_code.strip().upper() if asset_code else None

    resolved_run_id = run_id or str(uuid4())

    if thread_id is None:
        normalized_thread_id = resolved_run_id
    else:
        normalized_thread_id = thread_id.strip()

        if not normalized_thread_id:
            raise ValueError("thread_id must contain non-whitespace characters.")

    return AgentState(
        messages=[HumanMessage(content=normalized_query)],
        run_id=resolved_run_id,
        thread_id=normalized_thread_id,
        user_query=normalized_query,
        asset_code=normalized_asset_code,
        iteration_count=0,
        max_iterations=max_iterations,
        status=AgentStatus.PENDING,
        route=None,
        visited_nodes=[],
        error=None,
        evidence_ledger=[],
        evidence_coverage=None,
        grounding_result=None,
        diagnosis=None,
        work_order_proposal=None,
        approval_interrupt=None,
        approval_decision=None,
    )
