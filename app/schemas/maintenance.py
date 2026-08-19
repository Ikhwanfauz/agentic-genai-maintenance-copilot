from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import MaintenanceType
from app.schemas.common import AssetCodeInput


class MaintenanceHistoryInput(AssetCodeInput):
    maintenance_type: MaintenanceType | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = Field(default=10, ge=1, le=50)

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.start_time > self.end_time
        ):
            raise ValueError("start_time must be earlier than or equal to end_time.")

        return self


class MaintenanceRecordOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    performed_at: datetime
    maintenance_type: MaintenanceType
    summary: str
    findings: str
    action_taken: str
    technician: str
    downtime_hours: float


class MaintenanceHistoryOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_code: str
    total_matching_records: int
    returned_record_count: int
    has_more: bool
    records: list[MaintenanceRecordOutput] = Field(default_factory=list)
