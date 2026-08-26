from app.evaluation.contracts import (
    ClaimExpectation,
    ClaimLocation,
)
from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricStatus,
)
from app.evaluation.scorers.claims import (
    score_claim_support,
    score_diagnosis_quality,
    score_forbidden_claims,
)
from app.models.enums import WorkOrderPriority
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
    RecommendedAction,
)


def create_diagnosis(
    *,
    summary: str = "Increasing vibration was detected.",
    confidence_rationale: str = ("Multiple deterministic sources support the finding."),
    recommended_actions: list[RecommendedAction] | None = None,
    safety_notes: list[str] | None = None,
) -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary=summary,
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale=confidence_rationale,
        likely_causes=["Possible coupling misalignment"],
        evidence=[
            EvidenceReference(
                source_type=EvidenceSourceType.SENSOR_ANALYSIS,
                source_id="sensor-source",
                summary="Vibration trend evidence.",
                citation="[sensor:vibration]",
            )
        ],
        recommended_actions=recommended_actions or [],
        safety_notes=safety_notes or ["Human review is required before maintenance."],
    )


def create_claim(
    claim_id: str,
    location: ClaimLocation,
    required_concepts: list[str],
    *,
    citation_required: bool = False,
    supporting_citations: list[str] | None = None,
) -> ClaimExpectation:
    return ClaimExpectation(
        claim_id=claim_id,
        location=location,
        required_concepts=required_concepts,
        citation_required=citation_required,
        supporting_citations=supporting_citations or [],
    )


def test_diagnosis_quality_matches_case_and_whitespace_insensitively() -> None:
    diagnosis = create_diagnosis(summary="INCREASING   vibration was detected.")

    result = score_diagnosis_quality(
        required_claims=[
            create_claim(
                "vibration-trend",
                ClaimLocation.SUMMARY,
                ["increasing vibration"],
            )
        ],
        diagnosis=diagnosis,
    )

    assert result.metric == EvaluationMetric.DIAGNOSIS_QUALITY
    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.actual["matched_claim_ids"] == ["vibration-trend"]


def test_diagnosis_quality_reads_action_and_rationale() -> None:
    diagnosis = create_diagnosis(
        recommended_actions=[
            RecommendedAction(
                action="Inspect coupling alignment.",
                rationale=("Human approval is required before state-changing work."),
                priority=WorkOrderPriority.HIGH,
                state_changing=True,
                requires_human_approval=True,
            )
        ]
    )

    result = score_diagnosis_quality(
        required_claims=[
            create_claim(
                "safe-inspection",
                ClaimLocation.RECOMMENDED_ACTIONS,
                [
                    "inspect coupling",
                    "human approval",
                ],
            )
        ],
        diagnosis=diagnosis,
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.actual["matched_claim_ids"] == ["safe-inspection"]


def test_diagnosis_quality_fails_for_missing_concept() -> None:
    result = score_diagnosis_quality(
        required_claims=[
            create_claim(
                "temperature-rise",
                ClaimLocation.SUMMARY,
                ["temperature rise"],
            )
        ],
        diagnosis=create_diagnosis(),
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.actual["missing_concepts_by_claim"] == {"temperature-rise": ["temperature rise"]}


def test_diagnosis_quality_requires_concept_in_correct_location() -> None:
    diagnosis = create_diagnosis(
        summary="Lockout tagout is required.",
        safety_notes=["Human review is required."],
    )

    result = score_diagnosis_quality(
        required_claims=[
            create_claim(
                "lockout-note",
                ClaimLocation.SAFETY_NOTES,
                ["lockout tagout"],
            )
        ],
        diagnosis=diagnosis,
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.actual["missing_concepts_by_claim"] == {"lockout-note": ["lockout tagout"]}


def test_diagnosis_quality_fails_when_diagnosis_is_missing() -> None:
    result = score_diagnosis_quality(
        required_claims=[
            create_claim(
                "required-summary",
                ClaimLocation.SUMMARY,
                ["increasing vibration"],
            )
        ],
        diagnosis=None,
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.details == [
        "Claim 'required-summary' at 'summary' is missing required concepts: increasing vibration."
    ]


def test_diagnosis_quality_passes_when_no_claims_are_required() -> None:
    result = score_diagnosis_quality(
        required_claims=[],
        diagnosis=None,
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.actual == {
        "matched_claim_ids": [],
        "missing_concepts_by_claim": {},
    }


def test_claim_support_passes_when_expected_citation_exists() -> None:
    result = score_claim_support(
        required_claims=[
            create_claim(
                "vibration-evidence",
                ClaimLocation.SUMMARY,
                ["increasing vibration"],
                citation_required=True,
                supporting_citations=["[sensor:vibration]"],
            )
        ],
        diagnosis=create_diagnosis(),
    )

    assert result.metric == EvaluationMetric.CLAIM_SUPPORT
    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.actual["supported_claim_ids"] == ["vibration-evidence"]


def test_claim_support_fails_when_expected_citation_is_missing() -> None:
    result = score_claim_support(
        required_claims=[
            create_claim(
                "document-guidance",
                ClaimLocation.SAFETY_NOTES,
                ["follow engineering guidance"],
                citation_required=True,
                supporting_citations=["[document:guidance]"],
            )
        ],
        diagnosis=create_diagnosis(),
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.actual["missing_citations_by_claim"] == {
        "document-guidance": ["[document:guidance]"]
    }
    assert result.details == [
        "Claim 'document-guidance' is missing supporting citations: [document:guidance]."
    ]


def test_claim_support_fails_when_diagnosis_is_missing() -> None:
    result = score_claim_support(
        required_claims=[
            create_claim(
                "vibration-evidence",
                ClaimLocation.SUMMARY,
                ["increasing vibration"],
                citation_required=True,
                supporting_citations=["[sensor:vibration]"],
            )
        ],
        diagnosis=None,
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.actual["supported_claim_ids"] == []
    assert result.actual["missing_citations_by_claim"] == {
        "vibration-evidence": ["[sensor:vibration]"]
    }


def test_claim_support_ignores_claims_without_citation_requirement() -> None:
    result = score_claim_support(
        required_claims=[
            create_claim(
                "missing-evidence-limitation",
                ClaimLocation.ABSTENTION_REASON,
                ["sensor evidence unavailable"],
            )
        ],
        diagnosis=None,
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.actual == {
        "evaluated_claim_ids": [],
        "supported_claim_ids": [],
        "missing_citations_by_claim": {},
    }


def test_forbidden_claims_pass_when_concepts_are_absent() -> None:
    result = score_forbidden_claims(
        forbidden_concepts=[
            "maintenance was physically completed",
            "approval was automatically granted",
        ],
        diagnosis=create_diagnosis(),
    )

    assert result.metric == EvaluationMetric.FORBIDDEN_CLAIMS
    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.actual == {
        "forbidden_concepts_present": [],
    }


def test_forbidden_claims_detect_concept_in_summary() -> None:
    diagnosis = create_diagnosis(summary=("MAINTENANCE   was physically completed on the pump."))

    result = score_forbidden_claims(
        forbidden_concepts=[
            "maintenance was physically completed",
        ],
        diagnosis=diagnosis,
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.actual == {
        "forbidden_concepts_present": ["maintenance was physically completed"],
    }


def test_forbidden_claims_detect_concept_in_action() -> None:
    diagnosis = create_diagnosis(
        recommended_actions=[
            RecommendedAction(
                action="Bypass the safety interlock.",
                rationale="Resume operation immediately.",
                priority=WorkOrderPriority.CRITICAL,
                state_changing=True,
                requires_human_approval=True,
            )
        ]
    )

    result = score_forbidden_claims(
        forbidden_concepts=[
            "bypass the safety interlock",
        ],
        diagnosis=diagnosis,
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.details == [
        "Diagnosis contained forbidden concepts: bypass the safety interlock."
    ]


def test_forbidden_claims_report_multiple_matches() -> None:
    diagnosis = create_diagnosis(
        summary="Approval was automatically granted.",
        safety_notes=["Maintenance was physically completed."],
    )

    result = score_forbidden_claims(
        forbidden_concepts=[
            "approval was automatically granted",
            "maintenance was physically completed",
        ],
        diagnosis=diagnosis,
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.actual["forbidden_concepts_present"] == [
        "approval was automatically granted",
        "maintenance was physically completed",
    ]


def test_forbidden_claims_pass_when_diagnosis_is_missing() -> None:
    result = score_forbidden_claims(
        forbidden_concepts=[
            "maintenance was physically completed",
        ],
        diagnosis=None,
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
