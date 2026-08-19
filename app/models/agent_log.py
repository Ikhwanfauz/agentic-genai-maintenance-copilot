from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import utc_now
from app.models.enums import (
    AgentRunStatus,
    AgentStepStatus,
    AgentStepType,
    ToolCallStatus,
)

if TYPE_CHECKING:
    from app.models.approval import Approval


def new_run_id() -> str:
    return str(uuid4())


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_agent_runs_duration_nonnegative",
        ),
        CheckConstraint(
            "prompt_tokens >= 0 AND completion_tokens >= 0 AND total_tokens >= 0",
            name="ck_agent_runs_tokens_nonnegative",
        ),
        CheckConstraint(
            "model_calls >= 0",
            name="ck_agent_runs_model_calls_nonnegative",
        ),
        CheckConstraint(
            "estimated_cost_usd >= 0",
            name="ck_agent_runs_cost_nonnegative",
        ),
        CheckConstraint(
            "status IN ('running', 'waiting_for_approval') OR completed_at IS NOT NULL",
            name="ck_agent_runs_completion_timestamp",
        ),
    )

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=new_run_id,
    )
    thread_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        SQLEnum(
            AgentRunStatus,
            name="agent_run_status_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=AgentRunStatus.RUNNING,
        nullable=False,
    )
    model_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_calls: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    estimated_cost_usd: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    steps: Mapped[list[AgentStep]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    tool_calls: Mapped[list[ToolCall]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "step_number",
            name="uq_agent_steps_run_step_number",
        ),
        CheckConstraint(
            "step_number > 0",
            name="ck_agent_steps_step_number_positive",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_agent_steps_duration_nonnegative",
        ),
        CheckConstraint(
            "status = 'running' OR completed_at IS NOT NULL",
            name="ck_agent_steps_completion_timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[AgentStepType] = mapped_column(
        SQLEnum(
            AgentStepType,
            name="agent_step_type_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    status: Mapped[AgentStepStatus] = mapped_column(
        SQLEnum(
            AgentStepStatus,
            name="agent_step_status_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=AgentStepStatus.RUNNING,
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[AgentRun] = relationship(back_populates="steps")
    tool_calls: Mapped[list[ToolCall]] = relationship(back_populates="step")


class ToolCall(Base):
    __tablename__ = "tool_calls"
    __table_args__ = (
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_tool_calls_latency_nonnegative",
        ),
        CheckConstraint(
            "status = 'requested' OR completed_at IS NOT NULL",
            name="ck_tool_calls_completion_timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_steps.id", ondelete="SET NULL"),
        nullable=True,
    )
    approval_id: Mapped[int | None] = mapped_column(
        ForeignKey("approvals.id", ondelete="RESTRICT"),
        nullable=True,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    arguments_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    status: Mapped[ToolCallStatus] = mapped_column(
        SQLEnum(
            ToolCallStatus,
            name="tool_call_status_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=ToolCallStatus.REQUESTED,
        nullable=False,
    )
    is_state_changing: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(150), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[AgentRun] = relationship(back_populates="tool_calls")
    step: Mapped[AgentStep | None] = relationship(back_populates="tool_calls")
    approval: Mapped[Approval | None] = relationship()
