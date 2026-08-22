from collections.abc import Sequence

from app.schemas.diagnosis import EvidenceSourceType
from app.schemas.evidence import CollectedEvidence
from app.schemas.investigation import (
    EvidenceCoverage,
    EvidenceCoverageDecision,
)

REQUIRED_INVESTIGATION_SOURCES = (
    EvidenceSourceType.ASSET_DETAILS,
    EvidenceSourceType.MAINTENANCE_HISTORY,
    EvidenceSourceType.SENSOR_ANALYSIS,
    EvidenceSourceType.ENGINEERING_DOCUMENT,
)


def evaluate_evidence_coverage(
    evidence_ledger: Sequence[CollectedEvidence],
    target_asset_code: str | None,
) -> EvidenceCoverage:
    """Evaluate source coverage without inferring a fault or diagnosis."""

    if target_asset_code is None:
        return EvidenceCoverage(
            decision=EvidenceCoverageDecision.ASSET_SCOPE_REQUIRED,
            target_asset_code=None,
            required_sources=list(REQUIRED_INVESTIGATION_SOURCES),
            covered_sources=[],
            missing_sources=list(REQUIRED_INVESTIGATION_SOURCES),
            eligible_evidence_count=0,
            excluded_evidence_count=len(evidence_ledger),
            rationale=(
                "A target asset code is required before multi-source evidence "
                "coverage can be evaluated safely."
            ),
        )

    eligible_evidence = [
        evidence for evidence in evidence_ledger if evidence.asset_code == target_asset_code
    ]
    covered_source_set = {
        evidence.source_type
        for evidence in eligible_evidence
        if evidence.source_type in REQUIRED_INVESTIGATION_SOURCES
    }
    covered_sources = [
        source for source in REQUIRED_INVESTIGATION_SOURCES if source in covered_source_set
    ]
    missing_sources = [
        source for source in REQUIRED_INVESTIGATION_SOURCES if source not in covered_source_set
    ]
    decision = (
        EvidenceCoverageDecision.READY
        if not missing_sources
        else EvidenceCoverageDecision.INCOMPLETE
    )

    return EvidenceCoverage(
        decision=decision,
        target_asset_code=target_asset_code,
        required_sources=list(REQUIRED_INVESTIGATION_SOURCES),
        covered_sources=covered_sources,
        missing_sources=missing_sources,
        eligible_evidence_count=len(eligible_evidence),
        excluded_evidence_count=len(evidence_ledger) - len(eligible_evidence),
        rationale=(
            "All required evidence source categories are represented for the target asset."
            if decision == EvidenceCoverageDecision.READY
            else "Additional evidence source categories are required for grounded synthesis."
        ),
    )
