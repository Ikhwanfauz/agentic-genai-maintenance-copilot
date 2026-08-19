from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import AssetStatus, AssetType, Criticality
from app.schemas.common import AssetCodeInput


class AssetDetailsInput(AssetCodeInput):
    pass


class AssetDetailsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    asset_code: str
    name: str
    asset_type: AssetType
    status: AssetStatus
    criticality: Criticality
    location: str
    manufacturer: str | None
    model_number: str | None
    installation_date: date | None
    description: str | None
    parent_asset_code: str | None
    child_asset_codes: list[str] = Field(default_factory=list)
