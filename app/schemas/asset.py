from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import AssetStatus, AssetType, Criticality


class AssetDetailsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_code: str = Field(
        min_length=5,
        max_length=20,
        pattern=r"^[A-Z][A-Z0-9]*-\d{3}$",
        description="Unique equipment code, for example P-101.",
    )

    @field_validator("asset_code", mode="before")
    @classmethod
    def normalize_asset_code(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()

        return value


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
