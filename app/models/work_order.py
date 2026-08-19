from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin
from app.models.enums import WorkOrderPriority, WorkOrderStatus

if TYPE_CHECKING:
    from app.models.approval import Approval
    from app.models.asset import Asset


class WorkOrder(TimestampMixin, Base):
    __tablename__ = "work_orders"
    __table_args__ = (
        CheckConstraint(
            "revision > 0",
            name="ck_work_orders_revision_positive",
        ),
        CheckConstraint(
            "status != 'executed' OR executed_at IS NOT NULL",
            name="ck_work_orders_execution_timestamp",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    work_order_number: Mapped[str] = mapped_column(
        String(30),
        unique=True,
        index=True,
        nullable=False,
    )
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[WorkOrderPriority] = mapped_column(
        SQLEnum(
            WorkOrderPriority,
            name="work_order_priority_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    status: Mapped[WorkOrderStatus] = mapped_column(
        SQLEnum(
            WorkOrderStatus,
            name="work_order_status_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=WorkOrderStatus.PROPOSED,
        nullable=False,
    )
    revision: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
    )
    proposed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    execution_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    asset: Mapped[Asset] = relationship(back_populates="work_orders")
    approvals: Mapped[list[Approval]] = relationship(back_populates="work_order")
