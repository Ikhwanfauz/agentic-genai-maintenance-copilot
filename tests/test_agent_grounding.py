import json

from app.agent.grounding import (
    build_grounding_context_message,
    enforce_grounded_diagnosis,
)
from app.agent.policy import evaluate_evidence_coverage
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.evidence import CollectedEvidence
from app.schemas.investigation import GroundingDecision


def create_evidence(
    source_type: EvidenceSourceType,
    source_id: str,
    citation: str,
    *,
    asset_code: str = "P-101",
) -> CollectedEvidence:
    return CollectedEvidence(
        tool_call_id=f"call-{source_id}",
        tool_name="test_tool",
        source_type=source_type,
        source_id=source_id,
        citation=citation,
        asset_code=asset_code,
        payload={"source_id": source_id},
    )


def create_complete_ledger(
    asset_code: str = "P-101",
) -> list[CollectedEvidence]:
    return [
        create_evidence(
            EvidenceSourceType.ASSET_DETAILS,
            asset_code,
            f"asset:{asset_code}",
            asset_code=asset_code,
        ),
        create_evidence(
            EvidenceSourceType.MAINTENANCE_HISTORY,
            "7",
            "maintenance_record:7",
            asset_code=asset_code,
        ),
        create_evidence(
            EvidenceSourceType.SENSOR_ANALYSIS,
            f"{asset_code}:vibration",
            f"sensor:{asset_code}:vibration",
            asset_code=asset_code,
        ),
        create_evidence(
            EvidenceSourceType.ENGINEERING_DOCUMENT,
            "ENG-PUMP-001:elevated-vibration",
            (
                "ENG-PUMP-001 | Elevated Vibration | "
                "data/engineering_docs/pump_troubleshooting_guide.md"
            ),
            asset_code=asset_code,
        ),
    ]


def create_diagnosis(
    ledger: list[CollectedEvidence],
    *,
    asset_code: str = "P-101",
) -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code=asset_code,
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary="The evidence supports a developing mechanical vibration issue.",
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale="Four independent evidence categories are available.",
        likely_causes=["Developing coupling alignment or bearing condition issue"],
        evidence=[
            EvidenceReference(
                source_type=evidence.source_type,
                source_id=evidence.source_id,
                summary=f"Grounded evidence from {evidence.source_type.value}.",
                citation=evidence.citation,
            )
            for evidence in ledger
        ],
        recommended_actions=[],
        safety_notes=["Use approved isolation procedures before physical inspection."],
    )


def test_accepts_diagnosis_when_all_references_match_ready_ledger() -> None:
    ledger = create_complete_ledger()
    coverage = evaluate_evidence_coverage(ledger, "P-101")
    diagnosis = create_diagnosis(ledger)

    result, grounding = enforce_grounded_diagnosis(
        diagnosis,
        ledger,
        coverage,
        "P-101",
    )

    assert result is diagnosis
    assert result.outcome == InvestigationOutcome.DIAGNOSIS
    assert grounding.decision == GroundingDecision.GROUNDED
    assert grounding.downgraded is False
    assert grounding.violations == []
    assert len(grounding.matched_citations) == 4


def test_downgrades_diagnosis_when_coverage_is_incomplete() -> None:
    ledger = create_complete_ledger()[:1]
    coverage = evaluate_evidence_coverage(ledger, "P-101")
    diagnosis = create_diagnosis(ledger)

    result, grounding = enforce_grounded_diagnosis(
        diagnosis,
        ledger,
        coverage,
        "P-101",
    )

    assert result.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert result.confidence == DiagnosisConfidence.LOW
    assert grounding.decision == GroundingDecision.ABSTAINED
    assert grounding.downgraded is True
    assert any("coverage is incomplete" in violation for violation in grounding.violations)


def test_downgrades_diagnosis_with_invented_citation() -> None:
    ledger = create_complete_ledger()
    coverage = evaluate_evidence_coverage(ledger, "P-101")
    diagnosis = create_diagnosis(ledger)
    diagnosis.evidence[2].citation = "sensor:P-101:invented"

    result, grounding = enforce_grounded_diagnosis(
        diagnosis,
        ledger,
        coverage,
        "P-101",
    )

    assert result.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert grounding.downgraded is True
    assert len(grounding.matched_citations) == 3
    assert any("do not match" in violation for violation in grounding.violations)
    assert any("sensor_analysis" in violation for violation in grounding.violations)


def test_downgrades_diagnosis_with_duplicate_reference() -> None:
    ledger = create_complete_ledger()
    coverage = evaluate_evidence_coverage(ledger, "P-101")
    diagnosis = create_diagnosis(ledger)
    diagnosis.evidence.append(diagnosis.evidence[0].model_copy())

    result, grounding = enforce_grounded_diagnosis(
        diagnosis,
        ledger,
        coverage,
        "P-101",
    )

    assert result.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert grounding.downgraded is True
    assert any("Duplicate" in violation for violation in grounding.violations)


def test_downgrades_cross_asset_diagnosis() -> None:
    ledger = create_complete_ledger("P-102")
    coverage = evaluate_evidence_coverage(ledger, "P-101")
    diagnosis = create_diagnosis(ledger, asset_code="P-102")

    result, grounding = enforce_grounded_diagnosis(
        diagnosis,
        ledger,
        coverage,
        "P-101",
    )

    assert result.asset_code == "P-101"
    assert result.outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert grounding.matched_citations == []
    assert any("asset does not match" in violation for violation in grounding.violations)


def test_preserves_model_abstention_without_claiming_grounded_diagnosis() -> None:
    diagnosis = MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE,
        summary="Additional sensor evidence is required.",
        confidence=DiagnosisConfidence.LOW,
        confidence_rationale="Sensor evidence is unavailable.",
        safety_notes=["Do not act before collecting more evidence."],
        abstention_reason="Required sensor evidence is missing.",
    )

    result, grounding = enforce_grounded_diagnosis(
        diagnosis,
        [],
        evaluate_evidence_coverage([], "P-101"),
        "P-101",
    )

    assert result is diagnosis
    assert grounding.decision == GroundingDecision.ABSTAINED
    assert grounding.downgraded is False
    assert grounding.violations == []


def test_preserves_out_of_scope_outcome_without_evidence_requirement() -> None:
    diagnosis = MaintenanceDiagnosis(
        asset_code=None,
        outcome=InvestigationOutcome.OUT_OF_SCOPE,
        summary="The request is outside rotating-equipment maintenance.",
        confidence=DiagnosisConfidence.LOW,
        confidence_rationale="The request does not concern a supported asset.",
        safety_notes=["No maintenance action was proposed."],
        abstention_reason="The request is outside the copilot scope.",
    )

    result, grounding = enforce_grounded_diagnosis(
        diagnosis,
        [],
        None,
        None,
    )

    assert result is diagnosis
    assert grounding.decision == GroundingDecision.OUT_OF_SCOPE
    assert grounding.downgraded is False
    assert grounding.violations == []


def test_grounding_context_contains_only_target_asset_allowlist() -> None:
    target_ledger = create_complete_ledger()
    other_asset_evidence = create_complete_ledger("P-102")[0]
    ledger = [*target_ledger, other_asset_evidence]
    coverage = evaluate_evidence_coverage(ledger, "P-101")

    message = build_grounding_context_message(ledger, coverage, "P-101")
    metadata = json.loads(message.content.split("\n", maxsplit=1)[1])

    assert metadata["target_asset_code"] == "P-101"
    assert metadata["coverage"]["decision"] == "ready"
    assert len(metadata["citation_allowlist"]) == 4
    assert all("payload" not in item for item in metadata["citation_allowlist"])
    assert all(item["asset_code"] == "P-101" for item in metadata["citation_allowlist"])
