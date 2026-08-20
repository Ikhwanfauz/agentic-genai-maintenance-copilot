import pytest
from pydantic import ValidationError

from app.models.enums import WorkOrderPriority
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
    RecommendedAction,
)


def create_evidence() -> EvidenceReference:
    return EvidenceReference(
        source_type=EvidenceSourceType.SENSOR_ANALYSIS,
        source_id="P-101:vibration",
        summary="Vibration increased by 61.9 percent during the analysis window.",
        citation="sensor:P-101:vibration",
    )


def create_action(
    *,
    state_changing: bool = False,
    requires_human_approval: bool = False,
) -> RecommendedAction:
    return RecommendedAction(
        action="Inspect pump and motor coupling alignment.",
        rationale="Correlated vibration can be associated with coupling misalignment.",
        priority=WorkOrderPriority.HIGH,
        state_changing=state_changing,
        requires_human_approval=requires_human_approval,
    )


def test_grounded_diagnosis_accepts_evidence_and_actions() -> None:
    diagnosis = MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary="Evidence indicates a developing pump or coupling vibration issue.",
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale=(
            "Sensor trend and engineering guidance support the finding, "
            "but physical inspection is still required."
        ),
        likely_causes=[
            "Pump bearing degradation",
            "Pump-motor coupling misalignment",
        ],
        evidence=[create_evidence()],
        recommended_actions=[create_action()],
        safety_notes=["Follow site isolation and lockout procedures before physical inspection."],
    )

    assert diagnosis.outcome == InvestigationOutcome.DIAGNOSIS
    assert diagnosis.evidence[0].citation == "sensor:P-101:vibration"
    assert len(diagnosis.likely_causes) == 2


def test_diagnosis_rejects_missing_evidence() -> None:
    with pytest.raises(
        ValidationError,
        match="at least one evidence reference",
    ):
        MaintenanceDiagnosis(
            asset_code="P-101",
            outcome=InvestigationOutcome.DIAGNOSIS,
            summary="A diagnosis without evidence must not be accepted.",
            confidence=DiagnosisConfidence.MEDIUM,
            confidence_rationale="The model claimed a cause without evidence.",
            likely_causes=["Bearing degradation"],
            evidence=[],
            safety_notes=["Physical inspection is required."],
        )


def test_non_diagnosis_requires_abstention_reason() -> None:
    with pytest.raises(
        ValidationError,
        match="abstention reason",
    ):
        MaintenanceDiagnosis(
            asset_code="P-101",
            outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE,
            summary="There is not enough evidence.",
            confidence=DiagnosisConfidence.LOW,
            confidence_rationale="No sensor evidence was available.",
            safety_notes=["Do not act on an ungrounded diagnosis."],
        )


def test_insufficient_evidence_accepts_low_confidence_abstention() -> None:
    diagnosis = MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE,
        summary="Available evidence is insufficient for a grounded diagnosis.",
        confidence=DiagnosisConfidence.LOW,
        confidence_rationale="Required vibration readings were unavailable.",
        recommended_actions=[
            create_action(),
        ],
        safety_notes=["Gather additional evidence before proposing maintenance work."],
        abstention_reason="No usable vibration readings were available.",
    )

    assert diagnosis.abstention_reason is not None
    assert diagnosis.confidence == DiagnosisConfidence.LOW


def test_abstention_rejects_non_low_confidence() -> None:
    with pytest.raises(
        ValidationError,
        match="must use low confidence",
    ):
        MaintenanceDiagnosis(
            outcome=InvestigationOutcome.OUT_OF_SCOPE,
            summary="The request is outside rotating-equipment maintenance scope.",
            confidence=DiagnosisConfidence.HIGH,
            confidence_rationale="The request concerns unsupported equipment.",
            safety_notes=["Refer the request to the appropriate engineering team."],
            abstention_reason="Unsupported maintenance domain.",
        )


def test_state_changing_action_requires_human_approval() -> None:
    with pytest.raises(
        ValidationError,
        match="must require human approval",
    ):
        create_action(
            state_changing=True,
            requires_human_approval=False,
        )
