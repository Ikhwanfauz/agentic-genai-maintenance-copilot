from datetime import datetime
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from app.models.enums import (
    AgentStepStatus,
    AgentStepType,
    ToolCallStatus,
)


class ObservabilityModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AgentStepRecordInput(ObservabilityModel):
    run_id: str = Field(
        min_length=1,
        max_length=36,
    )
    step_number: int = Field(gt=0)
    step_type: AgentStepType
    status: Literal[
        AgentStepStatus.COMPLETED,
        AgentStepStatus.FAILED,
        AgentStepStatus.SKIPPED,
    ]
    summary: str = Field(
        min_length=1,
        max_length=4000,
    )
    started_at: datetime
    completed_at: datetime
    duration_ms: int = Field(ge=0)
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
        "summary",
        "error_type",
        "error_message",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.split())

        return value

    @model_validator(mode="after")
    def enforce_step_lifecycle(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("Agent-step completion must not be earlier than its start.")

        if self.status == AgentStepStatus.FAILED:
            if self.error_type is None or self.error_message is None:
                raise ValueError("A failed agent step requires error details.")
        elif self.error_type is not None or self.error_message is not None:
            raise ValueError("A non-failed agent step must not contain error details.")

        return self


class ToolCallRecordInput(ObservabilityModel):
    run_id: str = Field(
        min_length=1,
        max_length=36,
    )
    step_id: int | None = Field(
        default=None,
        gt=0,
    )
    approval_id: int | None = Field(
        default=None,
        gt=0,
    )
    tool_name: str = Field(
        min_length=1,
        max_length=100,
    )
    arguments_json: dict[str, JsonValue]
    result_json: dict[str, JsonValue] | None = None
    status: Literal[
        ToolCallStatus.SUCCEEDED,
        ToolCallStatus.FAILED,
        ToolCallStatus.BLOCKED,
    ]
    is_state_changing: bool = False
    started_at: datetime
    completed_at: datetime
    latency_ms: int = Field(ge=0)
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
        "tool_name",
        "error_type",
        "error_message",
        mode="before",
    )
    @classmethod
    def normalize_text(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.split())

        return value

    @model_validator(mode="after")
    def enforce_tool_call_lifecycle(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("Tool-call completion must not be earlier than its start.")

        if (
            self.is_state_changing
            and self.status != ToolCallStatus.BLOCKED
            and self.approval_id is None
        ):
            raise ValueError("A non-blocked state-changing tool call requires an approval record.")

        if self.status == ToolCallStatus.SUCCEEDED:
            if self.result_json is None:
                raise ValueError("A successful tool call requires a result.")

            if self.error_type is not None or self.error_message is not None:
                raise ValueError("A successful tool call must not contain error details.")

        if self.status == ToolCallStatus.FAILED:
            if self.error_type is None or self.error_message is None:
                raise ValueError("A failed tool call requires error details.")

        if self.status == ToolCallStatus.BLOCKED and self.error_message is None:
            raise ValueError("A blocked tool call requires a reason.")

        return self
