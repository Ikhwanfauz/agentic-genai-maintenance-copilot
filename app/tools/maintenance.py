from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.maintenance import MaintenanceRecord
from app.schemas.maintenance import (
    MaintenanceHistoryInput,
    MaintenanceHistoryOutput,
    MaintenanceRecordOutput,
)
from app.tools.exceptions import AssetNotFoundError


def query_maintenance_history(
    database_session: Session,
    tool_input: MaintenanceHistoryInput,
) -> MaintenanceHistoryOutput:
    asset_id = database_session.scalar(
        select(Asset.id).where(Asset.asset_code == tool_input.asset_code)
    )

    if asset_id is None:
        raise AssetNotFoundError(tool_input.asset_code)

    filters = [
        MaintenanceRecord.asset_id == asset_id,
    ]

    if tool_input.maintenance_type is not None:
        filters.append(MaintenanceRecord.maintenance_type == tool_input.maintenance_type)

    if tool_input.start_time is not None:
        filters.append(MaintenanceRecord.performed_at >= tool_input.start_time)

    if tool_input.end_time is not None:
        filters.append(MaintenanceRecord.performed_at <= tool_input.end_time)

    total_matching_records = database_session.scalar(
        select(func.count()).select_from(MaintenanceRecord).where(*filters)
    )
    total_matching_records = int(total_matching_records or 0)

    statement = (
        select(MaintenanceRecord)
        .where(*filters)
        .order_by(
            MaintenanceRecord.performed_at.desc(),
            MaintenanceRecord.id.desc(),
        )
        .limit(tool_input.limit)
    )

    maintenance_records = database_session.scalars(statement).all()

    records = [
        MaintenanceRecordOutput(
            id=record.id,
            performed_at=record.performed_at,
            maintenance_type=record.maintenance_type,
            summary=record.summary,
            findings=record.findings,
            action_taken=record.action_taken,
            technician=record.technician,
            downtime_hours=record.downtime_hours,
        )
        for record in maintenance_records
    ]

    return MaintenanceHistoryOutput(
        asset_code=tool_input.asset_code,
        total_matching_records=total_matching_records,
        returned_record_count=len(records),
        has_more=total_matching_records > len(records),
        records=records,
    )
