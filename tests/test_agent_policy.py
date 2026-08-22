import pytest

from app.agent.policy import (
    REQUIRED_INVESTIGATION_SOURCES,
    evaluate_evidence_coverage,
)
from app.schemas.diagnosis import EvidenceSourceType
from app.schemas.evidence import CollectedEvidence
from app.schemas.investigation import EvidenceCoverageDecision


def create_evidence(
    source_type: EvidenceSourceType,
    *,
    asset_code: str = "P-101",
    suffix: str = "1",
) -> CollectedEvidence:
    return CollectedEvidence(
        tool_call_id=f"tool-call-{suffix}",
        tool_name="test_tool",
        source_type=source_type,
        source_id=f"source-{suffix}",
        citation=f"test:{suffix}",
        asset_code=asset_code,
        payload={"source": suffix},
    )


def test_coverage_is_incomplete_when_required_sources_are_missing() -> None:
    coverage = evaluate_evidence_coverage(
        [create_evidence(EvidenceSourceType.ASSET_DETAILS)],
        "P-101",
    )

    assert coverage.decision == EvidenceCoverageDecision.INCOMPLETE
    assert coverage.covered_sources == [EvidenceSourceType.ASSET_DETAILS]
    assert coverage.missing_sources == [
        EvidenceSourceType.MAINTENANCE_HISTORY,
        EvidenceSourceType.SENSOR_ANALYSIS,
        EvidenceSourceType.ENGINEERING_DOCUMENT,
    ]
    assert coverage.eligible_evidence_count == 1
    assert coverage.excluded_evidence_count == 0


def test_coverage_is_ready_when_all_source_categories_are_present() -> None:
    ledger = [
        create_evidence(source_type, suffix=str(index))
        for index, source_type in enumerate(
            REQUIRED_INVESTIGATION_SOURCES,
            start=1,
        )
    ]

    coverage = evaluate_evidence_coverage(ledger, "P-101")

    assert coverage.decision == EvidenceCoverageDecision.READY
    assert coverage.covered_sources == list(REQUIRED_INVESTIGATION_SOURCES)
    assert coverage.missing_sources == []
    assert coverage.eligible_evidence_count == 4


def test_coverage_excludes_evidence_from_another_asset() -> None:
    ledger = [
        create_evidence(EvidenceSourceType.ASSET_DETAILS),
        create_evidence(
            EvidenceSourceType.SENSOR_ANALYSIS,
            asset_code="P-102",
            suffix="2",
        ),
    ]

    coverage = evaluate_evidence_coverage(ledger, "P-101")

    assert coverage.decision == EvidenceCoverageDecision.INCOMPLETE
    assert coverage.covered_sources == [EvidenceSourceType.ASSET_DETAILS]
    assert EvidenceSourceType.SENSOR_ANALYSIS in coverage.missing_sources
    assert coverage.eligible_evidence_count == 1
    assert coverage.excluded_evidence_count == 1


@pytest.mark.parametrize("ledger_size", [0, 1])
def test_coverage_requires_target_asset_scope(ledger_size: int) -> None:
    ledger = [create_evidence(EvidenceSourceType.ASSET_DETAILS)] if ledger_size else []

    coverage = evaluate_evidence_coverage(ledger, None)

    assert coverage.decision == EvidenceCoverageDecision.ASSET_SCOPE_REQUIRED
    assert coverage.target_asset_code is None
    assert coverage.covered_sources == []
    assert coverage.missing_sources == list(REQUIRED_INVESTIGATION_SOURCES)
    assert coverage.eligible_evidence_count == 0
    assert coverage.excluded_evidence_count == ledger_size
