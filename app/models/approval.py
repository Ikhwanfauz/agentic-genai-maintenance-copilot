from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin
from app.models.enums import ApprovalDecision

if TYPE_CHECKING:
    from app.models.work_order import WorkOrder


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        UniqueConstraint(
            "work_order_id",
            "request_version",
            name="uq_approvals_work_order_version",
        ),
        CheckConstraint(
            "request_version > 0",
            name="ck_approvals_request_version_positive",
        ),
        CheckConstraint(
            "("
            "decision = 'pending' "
            "AND decided_at IS NULL "
            "AND decided_by IS NULL"
            ") OR ("
            "decision != 'pending' "
            "AND decided_at IS NOT NULL "
            "AND decided_by IS NOT NULL"
            ")",
            name="ck_approvals_decision_metadata",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_id: Mapped[int] = mapped_column(
        ForeignKey("work_orders.id", ondelete="RESTRICT"),
        nullable=False,
    )
    request_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    decision: Mapped[ApprovalDecision] = mapped_column(
        SQLEnum(
            ApprovalDecision,
            name="approval_decision_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=ApprovalDecision.PENDING,
        nullable=False,
    )
    approval_scope: Mapped[str] = mapped_column(
        String(100),
        default="execute_work_order",
        nullable=False,
    )
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    work_order: Mapped[WorkOrder] = relationship(back_populates="approvals")
