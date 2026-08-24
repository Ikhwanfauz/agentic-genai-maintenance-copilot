from collections.abc import Callable
from hashlib import sha256

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.agent.state import (
    AgentRoute,
    AgentState,
    AgentStatus,
)
from app.models.enums import WorkOrderPriority
from app.schemas.actions import WorkOrderProposalInput
from app.schemas.diagnosis import (
    InvestigationOutcome,
    MaintenanceDiagnosis,
    RecommendedAction,
)
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    GroundingDecision,
)
from app.services.exceptions import WorkOrderServiceError
from app.services.work_orders import (
    WorkOrderNumberFactory,
    generate_work_order_number,
    propose_work_order,
)

SessionFactory = Callable[[], Session]

_PRIORITY_RANK = {
    WorkOrderPriority.LOW: 1,
    WorkOrderPriority.MEDIUM: 2,
    WorkOrderPriority.HIGH: 3,
    WorkOrderPriority.CRITICAL: 4,
}


def _select_proposal_action(
    diagnosis: MaintenanceDiagnosis,
) -> RecommendedAction | None:
    eligible_actions = [
        action
        for action in diagnosis.recommended_actions
        if action.state_changing and action.requires_human_approval
    ]

    if not eligible_actions:
        return None

    return max(
        eligible_actions,
        key=lambda action: _PRIORITY_RANK[action.priority],
    )


def _build_proposal_title(
    asset_code: str,
    action: RecommendedAction,
) -> str:
    return f"{asset_code}: {action.action}"[:200]


def _build_proposal_description(
    diagnosis: MaintenanceDiagnosis,
    action: RecommendedAction,
) -> str:
    safety_text = "; ".join(diagnosis.safety_notes)

    description = "\n".join(
        [
            f"Action: {action.action}",
            f"Rationale: {action.rationale}",
            f"Diagnosis: {diagnosis.summary}",
            f"Safety: {safety_text}",
        ]
    )

    return description[:4000].strip()


def _build_idempotency_key(
    run_id: str,
    asset_code: str,
) -> str:
    source = f"{run_id}:{asset_code}:work-order-proposal:v1"
    digest = sha256(source.encode("utf-8")).hexdigest()[:32]

    return f"agent-proposal:{digest}"


def _proposal_failure(
    message: str,
) -> dict[str, object]:
    return {
        "status": AgentStatus.FAILED,
        "route": AgentRoute.END,
        "work_order_proposal": None,
        "visited_nodes": ["propose_work_order"],
        "error": message,
    }


def create_propose_work_order_node(
    session_factory: SessionFactory,
    *,
    proposed_by: str = "maintenance-agent",
    work_order_number_factory: WorkOrderNumberFactory = (generate_work_order_number),
) -> Callable[[AgentState], dict[str, object]]:
    def propose_from_diagnosis(
        state: AgentState,
    ) -> dict[str, object]:
        diagnosis_value = state["diagnosis"]
        grounding_value = state["grounding_result"]

        if diagnosis_value is None or grounding_value is None:
            return _proposal_failure(
                "A diagnosis and grounding result are required before work-order proposal."
            )

        try:
            diagnosis = MaintenanceDiagnosis.model_validate(diagnosis_value)
            grounding_result = DiagnosisGroundingResult.model_validate(grounding_value)
        except ValidationError as error:
            return _proposal_failure(f"Proposal source validation failed: {error}")

        if (
            diagnosis.outcome != InvestigationOutcome.DIAGNOSIS
            or grounding_result.decision != GroundingDecision.GROUNDED
            or grounding_result.downgraded
        ):
            return _proposal_failure(
                "Only a grounded completed diagnosis may create a work-order proposal."
            )

        asset_code = diagnosis.asset_code

        if asset_code is None:
            return _proposal_failure("A work-order proposal requires a diagnosed asset.")

        selected_action = _select_proposal_action(diagnosis)

        if selected_action is None:
            return {
                "status": AgentStatus.COMPLETED,
                "route": AgentRoute.END,
                "work_order_proposal": None,
                "visited_nodes": ["propose_work_order"],
                "error": None,
            }

        try:
            proposal_input = WorkOrderProposalInput(
                asset_code=asset_code,
                title=_build_proposal_title(
                    asset_code,
                    selected_action,
                ),
                description=_build_proposal_description(
                    diagnosis,
                    selected_action,
                ),
                priority=selected_action.priority,
                proposed_by=proposed_by,
                idempotency_key=_build_idempotency_key(
                    state["run_id"],
                    asset_code,
                ),
                source_run_id=state["run_id"],
                diagnosis=diagnosis,
                grounding_result=grounding_result,
                requires_human_approval=True,
                approval_scope="execute_work_order",
            )

            with session_factory() as database_session:
                proposal_output = propose_work_order(
                    database_session,
                    proposal_input,
                    work_order_number_factory=(work_order_number_factory),
                )
        except (
            ValidationError,
            WorkOrderServiceError,
        ) as error:
            return _proposal_failure(f"Work-order proposal failed: {error}")

        return {
            "status": AgentStatus.RUNNING,
            "route": AgentRoute.APPROVAL,
            "work_order_proposal": proposal_output,
            "visited_nodes": ["propose_work_order"],
            "error": None,
        }

    return propose_from_diagnosis
