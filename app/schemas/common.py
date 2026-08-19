from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssetCodeInput(BaseModel):
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
