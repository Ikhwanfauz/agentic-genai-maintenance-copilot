from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.asset import Asset
from app.models.enums import DataQuality, SensorType
from app.models.sensor import SensorReading
from app.schemas.maintenance import MaintenanceHistoryInput, MaintenanceHistoryOutput
from app.tools.exceptions import AssetNotFoundError
from app.tools.maintenance import query_maintenance_history

router = APIRouter(tags=["maintenance"])


@router.get("/assets/{asset_code}/last-service", response_model=MaintenanceHistoryOutput)
def get_last_service(
    asset_code: Annotated[str, Path(pattern=r"^[A-Z][A-Z0-9]*-\d{3}$")],
    database_session: Annotated[Session, Depends(get_db)],
) -> MaintenanceHistoryOutput:
    try:
        return query_maintenance_history(
            database_session,
            MaintenanceHistoryInput(asset_code=asset_code, limit=1),
        )
    except AssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset not found.") from exc


class LatestTemperatureOutput(BaseModel):
    asset_code: str
    reading_id: int
    value: float
    unit: str
    recorded_at: datetime


@router.get("/assets/{asset_code}/latest-temperature")
def get_latest_temperature(
    asset_code: Annotated[str, Path(pattern=r"^[A-Z][A-Z0-9]*-\d{3}$")],
    database_session: Annotated[Session, Depends(get_db)],
) -> LatestTemperatureOutput:
    reading = database_session.scalar(
        select(SensorReading)
        .join(Asset, Asset.id == SensorReading.asset_id)
        .where(
            Asset.asset_code == asset_code,
            SensorReading.sensor_type == SensorType.TEMPERATURE,
        )
        .order_by(SensorReading.recorded_at.desc())
        .limit(1)
    )

    if reading is None:
        raise HTTPException(status_code=404, detail="No temperature reading found.")

    if reading.quality != DataQuality.GOOD:
        raise HTTPException(
            status_code=409,
            detail="Latest temperature reading is not good quality.",
        )

    return LatestTemperatureOutput(
        asset_code=asset_code,
        reading_id=reading.id,
        value=reading.value,
        unit=reading.unit,
        recorded_at=reading.recorded_at,
    )
