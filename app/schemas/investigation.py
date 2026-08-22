from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.diagnosis import EvidenceSourceType


class EvidenceCoverageDecision(StrEnum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    ASSET_SCOPE_REQUIRED = "asset_scope_required"


class GroundingDecision(StrEnum):
    GROUNDED = "grounded"
    ABSTAINED = "abstained"
    OUT_OF_SCOPE = "out_of_scope"


class EvidenceCoverage(BaseModel):
    """Deterministic coverage result for one asset investigation."""

    model_config = ConfigDict(extra="forbid")

    decision: EvidenceCoverageDecision
    target_asset_code: str | None = Field(
        default=None,
        min_length=5,
        max_length=20,
        pattern=r"^[A-Z][A-Z0-9]*-\d{3}$",
    )
    required_sources: list[EvidenceSourceType] = Field(min_length=1)
    covered_sources: list[EvidenceSourceType]
    missing_sources: list[EvidenceSourceType]
    eligible_evidence_count: int = Field(ge=0)
    excluded_evidence_count: int = Field(ge=0)
    rationale: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_coverage_contract(self) -> Self:
        required = set(self.required_sources)
        covered = set(self.covered_sources)
        missing = set(self.missing_sources)

        if covered & missing:
            raise ValueError("Covered and missing evidence sources must not overlap.")

        if covered | missing != required:
            raise ValueError("Covered and missing sources must partition required sources.")

        if self.decision == EvidenceCoverageDecision.READY and missing:
            raise ValueError("Ready evidence coverage must not contain missing sources.")

        if self.decision != EvidenceCoverageDecision.READY and not missing:
            raise ValueError("Non-ready evidence coverage must contain missing sources.")

        if (
            self.decision == EvidenceCoverageDecision.ASSET_SCOPE_REQUIRED
            and self.target_asset_code is not None
        ):
            raise ValueError("Asset-scope-required coverage must not have a target asset.")

        return self


class DiagnosisGroundingResult(BaseModel):
    """Application-owned audit result for one structured diagnosis."""

    model_config = ConfigDict(extra="forbid")

    decision: GroundingDecision
    original_outcome: str = Field(min_length=1, max_length=100)
    final_outcome: str = Field(min_length=1, max_length=100)
    matched_citations: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    downgraded: bool
