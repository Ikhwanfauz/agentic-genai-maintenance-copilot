from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from app.models.enums import (
    ApprovalDecision,
    WorkOrderPriority,
    WorkOrderStatus,
)
from app.schemas.common import AssetCodeInput
from app.schemas.diagnosis import (
    InvestigationOutcome,
    MaintenanceDiagnosis,
)
from app.schemas.investigation import (
    DiagnosisGroundingResult,
    GroundingDecision,
)


class WorkOrderProposalInput(AssetCodeInput):
    title: str = Field(
        min_length=5,
        max_length=200,
    )
    description: str = Field(
        min_length=10,
        max_length=4000,
    )
    priority: WorkOrderPriority
    proposed_by: str = Field(
        min_length=1,
        max_length=100,
    )
    idempotency_key: str = Field(
        min_length=8,
        max_length=100,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$",
    )
    source_run_id: str = Field(
        min_length=1,
        max_length=100,
    )
    diagnosis: MaintenanceDiagnosis
    grounding_result: DiagnosisGroundingResult
    requires_human_approval: Literal[True] = True
    approval_scope: Literal["execute_work_order"] = "execute_work_order"

    @field_validator(
        "title",
        "description",
        mode="before",
    )
    @classmethod
    def normalize_human_text(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.split())

        return value

    @field_validator(
        "proposed_by",
        "idempotency_key",
        "source_run_id",
        mode="before",
    )
    @classmethod
    def strip_identifier_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value

    @model_validator(mode="after")
    def enforce_grounded_proposal_boundary(self) -> Self:
        if self.diagnosis.outcome != InvestigationOutcome.DIAGNOSIS:
            raise ValueError("A work-order proposal requires a completed diagnosis.")

        if self.diagnosis.asset_code != self.asset_code:
            raise ValueError("The proposal asset must match the diagnosis asset.")

        if self.grounding_result.decision != GroundingDecision.GROUNDED:
            raise ValueError("A work-order proposal requires a grounded diagnosis.")

        if self.grounding_result.downgraded:
            raise ValueError("A downgraded diagnosis must not create a work-order proposal.")

        if self.grounding_result.violations:
            raise ValueError("A diagnosis with grounding violations must not create a proposal.")

        if (
            self.grounding_result.original_outcome != InvestigationOutcome.DIAGNOSIS.value
            or self.grounding_result.final_outcome != InvestigationOutcome.DIAGNOSIS.value
        ):
            raise ValueError("Grounding outcomes must confirm a completed diagnosis.")

        diagnosis_citations = sorted(evidence.citation for evidence in self.diagnosis.evidence)
        matched_citations = sorted(self.grounding_result.matched_citations)

        if diagnosis_citations != matched_citations:
            raise ValueError("The proposal diagnosis citations must match the grounding audit.")

        return self


class WorkOrderProposalOutput(AssetCodeInput):
    work_order_id: int = Field(gt=0)
    work_order_number: str = Field(
        min_length=1,
        max_length=30,
    )
    title: str = Field(
        min_length=5,
        max_length=200,
    )
    description: str = Field(
        min_length=10,
        max_length=4000,
    )
    priority: WorkOrderPriority
    status: Literal[WorkOrderStatus.PENDING_APPROVAL] = WorkOrderStatus.PENDING_APPROVAL
    revision: int = Field(gt=0)
    proposed_by: str = Field(
        min_length=1,
        max_length=100,
    )
    idempotency_key: str = Field(
        min_length=8,
        max_length=100,
    )
    approval_id: int = Field(gt=0)
    approval_decision: Literal[ApprovalDecision.PENDING] = ApprovalDecision.PENDING
    request_version: int = Field(gt=0)
    approval_scope: Literal["execute_work_order"] = "execute_work_order"
    created_new: bool
