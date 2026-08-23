import pytest
from pydantic import ValidationError

from app.models.enums import (
    ApprovalDecision,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.schemas.actions import (
    WorkOrderProposalInput,
    WorkOrderProposalOutput,
)
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    GroundingDecision,
)


def create_diagnosis() -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary="Evidence supports a developing vibration condition.",
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale=("Sensor analysis and engineering evidence support inspection."),
        likely_causes=["Developing coupling alignment or bearing condition issue"],
        evidence=[
            EvidenceReference(
                source_type=EvidenceSourceType.SENSOR_ANALYSIS,
                source_id="P-101:vibration",
                summary="P-101 vibration increased during the analysis window.",
                citation="sensor:P-101:vibration",
            )
        ],
        recommended_actions=[],
        safety_notes=["Use approved isolation procedures before physical inspection."],
    )


def create_grounding_result() -> DiagnosisGroundingResult:
    return DiagnosisGroundingResult(
        decision=GroundingDecision.GROUNDED,
        original_outcome=InvestigationOutcome.DIAGNOSIS.value,
        final_outcome=InvestigationOutcome.DIAGNOSIS.value,
        matched_citations=["sensor:P-101:vibration"],
        violations=[],
        downgraded=False,
    )


def create_proposal_input(
    **overrides: object,
) -> WorkOrderProposalInput:
    values: dict[str, object] = {
        "asset_code": "p-101",
        "title": "  Inspect elevated P-101 vibration  ",
        "description": (
            "  Inspect pump bearings, coupling alignment, and lubrication condition.  "
        ),
        "priority": WorkOrderPriority.HIGH,
        "proposed_by": " maintenance-agent ",
        "idempotency_key": " p101-vibration-run-001 ",
        "source_run_id": " run-001 ",
        "diagnosis": create_diagnosis(),
        "grounding_result": create_grounding_result(),
        "requires_human_approval": True,
    }
    values.update(overrides)

    return WorkOrderProposalInput.model_validate(values)


def test_grounded_work_order_proposal_is_accepted() -> None:
    proposal = create_proposal_input()

    assert proposal.asset_code == "P-101"
    assert proposal.title == "Inspect elevated P-101 vibration"
    assert proposal.proposed_by == "maintenance-agent"
    assert proposal.idempotency_key == "p101-vibration-run-001"
    assert proposal.requires_human_approval is True
    assert proposal.approval_scope == "execute_work_order"


def test_proposal_rejects_abstained_diagnosis() -> None:
    diagnosis = MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE,
        summary="Evidence is incomplete.",
        confidence=DiagnosisConfidence.LOW,
        confidence_rationale="Required sensor evidence is missing.",
        safety_notes=["Do not create maintenance work from incomplete evidence."],
        abstention_reason="Sensor evidence is unavailable.",
    )

    with pytest.raises(
        ValidationError,
        match="requires a completed diagnosis",
    ):
        create_proposal_input(diagnosis=diagnosis)


def test_proposal_rejects_asset_mismatch() -> None:
    with pytest.raises(
        ValidationError,
        match="proposal asset must match",
    ):
        create_proposal_input(asset_code="P-102")


def test_proposal_rejects_ungrounded_result() -> None:
    grounding_result = DiagnosisGroundingResult(
        decision=GroundingDecision.ABSTAINED,
        original_outcome=InvestigationOutcome.DIAGNOSIS.value,
        final_outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE.value,
        matched_citations=[],
        violations=["Evidence coverage is incomplete."],
        downgraded=True,
    )

    with pytest.raises(
        ValidationError,
        match="requires a grounded diagnosis",
    ):
        create_proposal_input(
            grounding_result=grounding_result,
        )


def test_proposal_rejects_citation_mismatch() -> None:
    grounding_result = create_grounding_result()
    grounding_result.matched_citations = ["sensor:P-101:invented"]

    with pytest.raises(
        ValidationError,
        match="citations must match",
    ):
        create_proposal_input(
            grounding_result=grounding_result,
        )


def test_proposal_cannot_disable_human_approval() -> None:
    with pytest.raises(ValidationError):
        create_proposal_input(
            requires_human_approval=False,
        )


def test_proposal_output_requires_pending_states() -> None:
    output = WorkOrderProposalOutput(
        work_order_id=10,
        work_order_number="WO-PROP-0010",
        asset_code="P-101",
        title="Inspect elevated P-101 vibration",
        description=("Inspect pump bearings, coupling alignment, and lubrication condition."),
        priority=WorkOrderPriority.HIGH,
        status=WorkOrderStatus.PENDING_APPROVAL,
        revision=1,
        proposed_by="maintenance-agent",
        idempotency_key="p101-vibration-run-001",
        approval_id=5,
        approval_decision=ApprovalDecision.PENDING,
        request_version=1,
        approval_scope="execute_work_order",
        created_new=True,
    )

    assert output.status == WorkOrderStatus.PENDING_APPROVAL
    assert output.approval_decision == ApprovalDecision.PENDING

    with pytest.raises(ValidationError):
        WorkOrderProposalOutput(
            **{
                **output.model_dump(),
                "status": WorkOrderStatus.APPROVED,
            }
        )
