from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricStatus,
)
from app.evaluation.scorers.evidence import (
    score_citation_completeness,
    score_citation_validity,
    score_evidence_coverage,
)
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.evidence import CollectedEvidence


def create_evidence(
    source_type: EvidenceSourceType,
    *,
    asset_code: str | None = "P-101",
) -> CollectedEvidence:
    return CollectedEvidence(
        tool_call_id=f"call-{source_type.value}",
        tool_name="deterministic_test_tool",
        source_type=source_type,
        source_id=f"source-{source_type.value}",
        citation=f"[{source_type.value}:source]",
        asset_code=asset_code,
        payload={"fixture": True},
    )


def create_reference(
    source_type: EvidenceSourceType,
    *,
    source_id: str | None = None,
    citation: str | None = None,
) -> EvidenceReference:
    resolved_source_id = source_id or f"source-{source_type.value}"
    resolved_citation = citation or f"[{source_type.value}:source]"

    return EvidenceReference(
        source_type=source_type,
        source_id=resolved_source_id,
        summary="Deterministic evaluation reference.",
        citation=resolved_citation,
    )


def create_diagnosis(
    evidence: list[EvidenceReference],
) -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary="A grounded test diagnosis.",
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale="The diagnosis uses deterministic fixture evidence.",
        likely_causes=["Fixture cause"],
        evidence=evidence,
        recommended_actions=[],
        safety_notes=["Human review remains required."],
    )


def test_evidence_coverage_passes_when_required_sources_are_present() -> None:
    result = score_evidence_coverage(
        expected_sources=[
            EvidenceSourceType.ASSET_DETAILS,
            EvidenceSourceType.SENSOR_ANALYSIS,
        ],
        evidence_ledger=[
            create_evidence(EvidenceSourceType.ASSET_DETAILS),
            create_evidence(EvidenceSourceType.SENSOR_ANALYSIS),
            create_evidence(
                EvidenceSourceType.MAINTENANCE_HISTORY,
                asset_code="P-201",
            ),
        ],
        target_asset_code="P-101",
    )

    assert result.metric == EvaluationMetric.EVIDENCE_COVERAGE
    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.expected == [
        "asset_details",
        "sensor_analysis",
    ]
    assert result.actual == [
        "asset_details",
        "sensor_analysis",
    ]
    assert result.details == []


def test_evidence_coverage_fails_when_required_source_is_missing() -> None:
    result = score_evidence_coverage(
        expected_sources=[
            EvidenceSourceType.ASSET_DETAILS,
            EvidenceSourceType.SENSOR_ANALYSIS,
        ],
        evidence_ledger=[
            create_evidence(EvidenceSourceType.ASSET_DETAILS),
        ],
        target_asset_code="P-101",
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.actual == ["asset_details"]
    assert result.details == ["Missing required evidence sources: sensor_analysis."]


def test_evidence_coverage_excludes_evidence_from_another_asset() -> None:
    result = score_evidence_coverage(
        expected_sources=[
            EvidenceSourceType.SENSOR_ANALYSIS,
        ],
        evidence_ledger=[
            create_evidence(
                EvidenceSourceType.SENSOR_ANALYSIS,
                asset_code="P-201",
            ),
        ],
        target_asset_code="P-101",
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.actual == []
    assert result.details == ["Missing required evidence sources: sensor_analysis."]


def test_evidence_coverage_passes_when_no_sources_are_required() -> None:
    result = score_evidence_coverage(
        expected_sources=[],
        evidence_ledger=[],
        target_asset_code=None,
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.expected == []
    assert result.actual == []


def test_citation_validity_passes_for_exact_eligible_match() -> None:
    diagnosis = create_diagnosis([create_reference(EvidenceSourceType.SENSOR_ANALYSIS)])

    result = score_citation_validity(
        diagnosis=diagnosis,
        evidence_ledger=[
            create_evidence(EvidenceSourceType.SENSOR_ANALYSIS),
        ],
        target_asset_code="P-101",
    )

    assert result.metric == EvaluationMetric.CITATION_VALIDITY
    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.actual == {
        "invalid_references": [],
        "duplicate_references": [],
    }


def test_citation_validity_fails_for_wrong_source_id() -> None:
    diagnosis = create_diagnosis(
        [
            create_reference(
                EvidenceSourceType.SENSOR_ANALYSIS,
                source_id="fabricated-source",
            )
        ]
    )

    result = score_citation_validity(
        diagnosis=diagnosis,
        evidence_ledger=[
            create_evidence(EvidenceSourceType.SENSOR_ANALYSIS),
        ],
        target_asset_code="P-101",
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.actual["invalid_references"] == [
        "sensor_analysis | fabricated-source | [sensor_analysis:source]"
    ]


def test_citation_validity_rejects_evidence_from_another_asset() -> None:
    diagnosis = create_diagnosis([create_reference(EvidenceSourceType.SENSOR_ANALYSIS)])

    result = score_citation_validity(
        diagnosis=diagnosis,
        evidence_ledger=[
            create_evidence(
                EvidenceSourceType.SENSOR_ANALYSIS,
                asset_code="P-201",
            ),
        ],
        target_asset_code="P-101",
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.actual["invalid_references"] == [
        "sensor_analysis | source-sensor_analysis | [sensor_analysis:source]"
    ]


def test_citation_validity_rejects_duplicate_references() -> None:
    reference = create_reference(EvidenceSourceType.SENSOR_ANALYSIS)
    diagnosis = create_diagnosis([reference, reference.model_copy()])

    result = score_citation_validity(
        diagnosis=diagnosis,
        evidence_ledger=[
            create_evidence(EvidenceSourceType.SENSOR_ANALYSIS),
        ],
        target_asset_code="P-101",
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.actual["invalid_references"] == []
    assert result.actual["duplicate_references"] == [
        "sensor_analysis | source-sensor_analysis | [sensor_analysis:source]"
    ]


def test_citation_validity_passes_when_no_diagnosis_exists() -> None:
    result = score_citation_validity(
        diagnosis=None,
        evidence_ledger=[],
        target_asset_code="P-101",
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0


def test_citation_completeness_passes_when_required_citations_exist() -> None:
    diagnosis = create_diagnosis(
        [
            create_reference(EvidenceSourceType.ASSET_DETAILS),
            create_reference(EvidenceSourceType.SENSOR_ANALYSIS),
        ]
    )

    result = score_citation_completeness(
        expected_citations=["[sensor_analysis:source]"],
        diagnosis=diagnosis,
    )

    assert result.metric == EvaluationMetric.CITATION_COMPLETENESS
    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.expected == ["[sensor_analysis:source]"]
    assert result.actual == [
        "[asset_details:source]",
        "[sensor_analysis:source]",
    ]


def test_citation_completeness_fails_when_required_citation_is_missing() -> None:
    diagnosis = create_diagnosis([create_reference(EvidenceSourceType.SENSOR_ANALYSIS)])

    result = score_citation_completeness(
        expected_citations=[
            "[engineering_document:source]",
            "[sensor_analysis:source]",
        ],
        diagnosis=diagnosis,
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.details == [
        "Missing required diagnosis citations: [engineering_document:source]."
    ]


def test_citation_completeness_fails_when_diagnosis_is_missing() -> None:
    result = score_citation_completeness(
        expected_citations=["[sensor_analysis:source]"],
        diagnosis=None,
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.actual == []
    assert result.details == ["Missing required diagnosis citations: [sensor_analysis:source]."]


def test_citation_completeness_passes_when_no_citations_are_required() -> None:
    result = score_citation_completeness(
        expected_citations=[],
        diagnosis=None,
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.expected == []
    assert result.actual == []
