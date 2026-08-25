import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver

_ALLOWED_MSGPACK_MODULES: tuple[tuple[str, ...], ...] = (
    (
        "app.agent.state",
        "AgentRoute",
    ),
    (
        "app.agent.state",
        "AgentStatus",
    ),
    (
        "app.models.enums",
        "ApprovalDecision",
    ),
    (
        "app.models.enums",
        "WorkOrderPriority",
    ),
    (
        "app.models.enums",
        "WorkOrderStatus",
    ),
    (
        "app.schemas.actions",
        "WorkOrderApprovalDecisionOutput",
    ),
    (
        "app.schemas.actions",
        "WorkOrderProposalOutput",
    ),
    (
        "app.schemas.diagnosis",
        "DiagnosisConfidence",
    ),
    (
        "app.schemas.diagnosis",
        "EvidenceReference",
    ),
    (
        "app.schemas.diagnosis",
        "EvidenceSourceType",
    ),
    (
        "app.schemas.diagnosis",
        "InvestigationOutcome",
    ),
    (
        "app.schemas.diagnosis",
        "MaintenanceDiagnosis",
    ),
    (
        "app.schemas.diagnosis",
        "RecommendedAction",
    ),
    (
        "app.schemas.evidence",
        "CollectedEvidence",
    ),
    (
        "app.schemas.hitl",
        "WorkOrderApprovalInterrupt",
    ),
    (
        "app.schemas.hitl",
        "WorkOrderApprovalResume",
    ),
    (
        "app.schemas.investigation",
        "DiagnosisGroundingResult",
    ),
    (
        "app.schemas.investigation",
        "EvidenceCoverage",
    ),
    (
        "app.schemas.investigation",
        "EvidenceCoverageDecision",
    ),
    (
        "app.schemas.investigation",
        "GroundingDecision",
    ),
)


def _resolve_checkpoint_path(
    checkpoint_path: str | Path,
) -> str:
    normalized_path = str(checkpoint_path).strip()

    if not normalized_path:
        raise ValueError("LangGraph checkpoint path must not be empty.")

    if normalized_path == ":memory:":
        return normalized_path

    resolved_path = Path(normalized_path)
    resolved_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    return str(resolved_path)


@contextmanager
def open_sqlite_checkpointer(
    checkpoint_path: str | Path,
) -> Iterator[SqliteSaver]:
    resolved_path = _resolve_checkpoint_path(checkpoint_path)
    connection = sqlite3.connect(
        resolved_path,
        check_same_thread=False,
    )
    serializer = JsonPlusSerializer(
        allowed_msgpack_modules=_ALLOWED_MSGPACK_MODULES,
    )
    checkpointer = SqliteSaver(
        connection,
        serde=serializer,
    )

    try:
        yield checkpointer
    finally:
        connection.close()
