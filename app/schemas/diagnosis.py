from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import WorkOrderPriority

ShortText = Annotated[
    str,
    Field(
        min_length=1,
        max_length=500,
    ),
]


class InvestigationOutcome(StrEnum):
    DIAGNOSIS = "diagnosis"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    OUT_OF_SCOPE = "out_of_scope"


class DiagnosisConfidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceSourceType(StrEnum):
    ASSET_DETAILS = "asset_details"
    MAINTENANCE_HISTORY = "maintenance_history"
    SENSOR_ANALYSIS = "sensor_analysis"
    ENGINEERING_DOCUMENT = "engineering_document"


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: EvidenceSourceType
    source_id: str = Field(
        min_length=1,
        max_length=200,
    )
    summary: str = Field(
        min_length=1,
        max_length=1000,
    )
    citation: str = Field(
        min_length=1,
        max_length=500,
    )


class RecommendedAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(
        min_length=1,
        max_length=500,
    )
    rationale: str = Field(
        min_length=1,
        max_length=1000,
    )
    priority: WorkOrderPriority
    state_changing: bool
    requires_human_approval: bool

    @model_validator(mode="after")
    def enforce_approval_boundary(self) -> Self:
        if self.state_changing and not self.requires_human_approval:
            raise ValueError("State-changing application actions must require human approval.")

        return self


class MaintenanceDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_code: str | None = Field(
        default=None,
        min_length=5,
        max_length=20,
        pattern=r"^[A-Z][A-Z0-9]*-\d{3}$",
    )
    outcome: InvestigationOutcome
    summary: str = Field(
        min_length=1,
        max_length=2000,
    )
    confidence: DiagnosisConfidence
    confidence_rationale: str = Field(
        min_length=1,
        max_length=1000,
    )
    likely_causes: list[ShortText] = Field(
        default_factory=list,
        max_length=5,
    )
    evidence: list[EvidenceReference] = Field(
        default_factory=list,
        max_length=20,
    )
    recommended_actions: list[RecommendedAction] = Field(
        default_factory=list,
        max_length=10,
    )
    safety_notes: list[ShortText] = Field(
        default_factory=list,
        min_length=1,
        max_length=10,
    )
    abstention_reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_outcome_contract(self) -> Self:
        if self.outcome == InvestigationOutcome.DIAGNOSIS:
            if not self.likely_causes:
                raise ValueError("A diagnosis must contain at least one likely cause.")

            if not self.evidence:
                raise ValueError("A diagnosis must contain at least one evidence reference.")

            if self.abstention_reason is not None:
                raise ValueError("A completed diagnosis must not contain an abstention reason.")

            return self

        if self.abstention_reason is None:
            raise ValueError("A non-diagnosis outcome must contain an abstention reason.")

        if self.confidence != DiagnosisConfidence.LOW:
            raise ValueError("An abstained investigation must use low confidence.")

        return self
