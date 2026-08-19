from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin
from app.models.enums import MaintenanceType

if TYPE_CHECKING:
    from app.models.asset import Asset


class MaintenanceRecord(TimestampMixin, Base):
    __tablename__ = "maintenance_records"
    __table_args__ = (
        CheckConstraint(
            "downtime_hours >= 0",
            name="ck_maintenance_records_downtime_nonnegative",
        ),
        Index(
            "ix_maintenance_records_asset_performed_at",
            "asset_id",
            "performed_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    performed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    maintenance_type: Mapped[MaintenanceType] = mapped_column(
        SQLEnum(
            MaintenanceType,
            name="maintenance_type_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    findings: Mapped[str] = mapped_column(Text, nullable=False)
    action_taken: Mapped[str] = mapped_column(Text, nullable=False)
    technician: Mapped[str] = mapped_column(String(100), nullable=False)
    downtime_hours: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    asset: Mapped[Asset] = relationship(back_populates="maintenance_records")
