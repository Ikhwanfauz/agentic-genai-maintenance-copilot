from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.db.session import get_db
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