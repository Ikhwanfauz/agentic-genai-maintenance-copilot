from datetime import datetime
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from app.models.enums import (
    AgentRunStatus,
    ApprovalDecision,
)
from app.schemas.actions import (
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)
from app.schemas.diagnosis import MaintenanceDiagnosis
from app.schemas.hitl import WorkOrderApprovalInterrupt


class AgentApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentInvestigationStartRequest(AgentApiModel):
    user_query: str = Field(
        min_length=1,
        max_length=4000,
    )
    asset_code: str | None = Field(
        default=None,
        min_length=5,
        max_length=20,
        pattern=r"^[A-Z][A-Z0-9]*-\d{3}$",
    )
    thread_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
    )
    max_iterations: int = Field(
        default=6,
        ge=1,
        le=10,
    )

    @field_validator("user_query", mode="before")
    @classmethod
    def normalize_user_query(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.split())

        return value

    @field_validator("asset_code", mode="before")
    @classmethod
    def normalize_asset_code(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()

        return value

    @field_validator("thread_id", mode="before")
    @classmethod
    def normalize_thread_id(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value


class AgentApprovalDecisionRequest(AgentApiModel):
    request_version: int = Field(gt=0)
    decision: Literal[
        ApprovalDecision.APPROVED,
        ApprovalDecision.REJECTED,
    ]
    decided_by: str = Field(
        min_length=1,
        max_length=100,
    )
    decision_reason: str = Field(
        min_length=5,
        max_length=2000,
    )
    decision_source: Literal["human"] = "human"
    approval_scope: Literal["execute_work_order"] = "execute_work_order"

    @field_validator(
        "decided_by",
        "decision_reason",
        mode="before",
    )
    @classmethod
    def normalize_human_text(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.split())

        return value


class AgentRunResponse(AgentApiModel):
    run_id: str = Field(
        min_length=1,
        max_length=100,
    )
    thread_id: str = Field(
        min_length=1,
        max_length=100,
    )
    status: AgentRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    diagnosis: MaintenanceDiagnosis | None = None
    work_order_proposal: WorkOrderProposalOutput | None = None
    approval_interrupt: WorkOrderApprovalInterrupt | None = None
    approval_decision: WorkOrderApprovalDecisionOutput | None = None
    final_response: str | None = Field(
        default=None,
        max_length=10000,
    )
    error_type: str | None = Field(
        default=None,
        max_length=150,
    )
    error_message: str | None = Field(
        default=None,
        max_length=4000,
    )

    @field_validator(
        "run_id",
        "thread_id",
        mode="before",
    )
    @classmethod
    def normalize_identifiers(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value

    @model_validator(mode="after")
    def enforce_run_lifecycle(self) -> Self:
        active_statuses = {
            AgentRunStatus.RUNNING,
            AgentRunStatus.WAITING_FOR_APPROVAL,
        }

        if self.status in active_statuses and self.completed_at is not None:
            raise ValueError("An active agent run must not have a completion timestamp.")

        if self.status not in active_statuses and self.completed_at is None:
            raise ValueError("A terminal agent run requires a completion timestamp.")

        if self.status == AgentRunStatus.WAITING_FOR_APPROVAL:
            if self.approval_interrupt is None:
                raise ValueError("A run waiting for approval requires an approval interrupt.")

            if self.work_order_proposal is None:
                raise ValueError("A run waiting for approval requires a work-order proposal.")

        if self.approval_interrupt is not None:
            if self.approval_interrupt.run_id != self.run_id:
                raise ValueError("The approval interrupt run ID does not match the run.")

            if self.approval_interrupt.thread_id != self.thread_id:
                raise ValueError("The approval interrupt thread ID does not match the run.")

        return self
