from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.actions import (
    WorkOrderApprovalDecisionOutput,
    WorkOrderProposalOutput,
)


class WorkOrderApprovalInterrupt(BaseModel):
    interrupt_type: Literal["work_order_approval_required"] = "work_order_approval_required"
    run_id: str = Field(
        min_length=1,
        max_length=100,
    )
    thread_id: str = Field(
        min_length=1,
        max_length=100,
    )
    proposal: WorkOrderProposalOutput

    validation_error: str | None = Field(
        default=None,
        min_length=1,
        max_length=2000,
    )

    @field_validator(
        "run_id",
        "thread_id",
        mode="before",
    )
    @classmethod
    def strip_identifiers(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value


class WorkOrderApprovalResume(BaseModel):
    resume_type: Literal["work_order_approval_decided"] = "work_order_approval_decided"
    run_id: str = Field(
        min_length=1,
        max_length=100,
    )
    thread_id: str = Field(
        min_length=1,
        max_length=100,
    )
    decision: WorkOrderApprovalDecisionOutput

    @field_validator(
        "run_id",
        "thread_id",
        mode="before",
    )
    @classmethod
    def strip_identifiers(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()

        return value
