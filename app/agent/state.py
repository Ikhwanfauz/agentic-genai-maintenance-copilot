from enum import StrEnum
from operator import add
from typing import Annotated
from uuid import uuid4

from langchain_core.messages import AnyMessage, HumanMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from app.schemas.diagnosis import MaintenanceDiagnosis
from app.schemas.evidence import CollectedEvidence
from app.schemas.investigation import EvidenceCoverage


class AgentStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"
    AWAITING_TOOL = "awaiting_tool"
    COMPLETED = "completed"
    LIMIT_REACHED = "limit_reached"
    FAILED = "failed"
    REJECTED = "rejected"


class AgentRoute(StrEnum):
    INVESTIGATE = "investigate"
    TOOLS = "tools"
    SYNTHESIZE = "synthesize"
    END = "end"


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    run_id: str
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
    diagnosis: MaintenanceDiagnosis | None


def create_initial_state(
    user_query: str,
    asset_code: str | None = None,
    *,
    max_iterations: int = 6,
    run_id: str | None = None,
) -> AgentState:
    if not 1 <= max_iterations <= 10:
        raise ValueError("max_iterations must be between 1 and 10.")

    normalized_query = user_query.strip()
    normalized_asset_code = asset_code.strip().upper() if asset_code else None

    return AgentState(
        messages=[HumanMessage(content=normalized_query)],
        run_id=run_id or str(uuid4()),
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
        diagnosis=None,
    )
