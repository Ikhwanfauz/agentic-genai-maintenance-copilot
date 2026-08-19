from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.common import TimestampMixin
from app.models.enums import DataQuality, SensorType

if TYPE_CHECKING:
    from app.models.asset import Asset


class SensorReading(TimestampMixin, Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "recorded_at",
            "sensor_type",
            name="uq_sensor_reading_asset_time_type",
        ),
        Index(
            "ix_sensor_readings_asset_recorded_at",
            "asset_id",
            "recorded_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    sensor_type: Mapped[SensorType] = mapped_column(
        SQLEnum(
            SensorType,
            name="sensor_type_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        nullable=False,
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(20), nullable=False)
    quality: Mapped[DataQuality] = mapped_column(
        SQLEnum(
            DataQuality,
            name="data_quality_enum",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda enum_class: [member.value for member in enum_class],
        ),
        default=DataQuality.GOOD,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(
        String(50),
        default="simulator",
        nullable=False,
    )

    asset: Mapped[Asset] = relationship(back_populates="sensor_readings")
