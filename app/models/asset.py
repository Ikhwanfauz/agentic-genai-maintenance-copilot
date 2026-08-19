from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin
from app.models.enums import AssetStatus, AssetType, Criticality

if TYPE_CHECKING:
    from app.models.maintenance import MaintenanceRecord
    from app.models.sensor import SensorReading
    from app.models.work_order import WorkOrder


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_code: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    asset_type: Mapped[AssetType] = mapped_column(
        SQLEnum(
            AssetType,
            name="asset_type_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    status: Mapped[AssetStatus] = mapped_column(
        SQLEnum(
            AssetStatus,
            name="asset_status_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    criticality: Mapped[Criticality] = mapped_column(
        SQLEnum(
            Criticality,
            name="criticality_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    location: Mapped[str] = mapped_column(String(150), nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    installation_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    parent_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    parent: Mapped[Asset | None] = relationship(
        remote_side=[id],
        back_populates="children",
    )
    children: Mapped[list[Asset]] = relationship(back_populates="parent")
    sensor_readings: Mapped[list[SensorReading]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
    )
    maintenance_records: Mapped[list[MaintenanceRecord]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
    )

    work_orders: Mapped[list[WorkOrder]] = relationship(back_populates="asset")
