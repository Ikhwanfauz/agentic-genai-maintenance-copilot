from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.common import AssetCodeInput


class EngineeringDocumentSearchInput(AssetCodeInput):
    asset_code: str | None = Field(
        default=None,
        min_length=5,
        max_length=20,
        pattern=r"^[A-Z][A-Z0-9]*-\d{3}$",
    )
    query: str = Field(
        min_length=3,
        max_length=500,
    )
    top_k: int = Field(default=3, ge=1, le=10)
    minimum_relevance: float = Field(
        default=0.25,
        ge=0.0,
        le=1.0,
    )

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> object:
        if isinstance(value, str):
            return " ".join(value.split())

        return value


class EngineeringDocumentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    document_id: str
    title: str
    section: str
    source_path: str
    applicable_assets: str
    content: str
    distance: float
    relevance_score: float
    citation: str


class EngineeringDocumentSearchOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    asset_code: str | None
    returned_result_count: int
    results: list[EngineeringDocumentResult] = Field(default_factory=list)
