from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.diagnosis import EvidenceSourceType


class CollectedEvidence(BaseModel):
    """One traceable evidence record captured from a deterministic tool result."""

    model_config = ConfigDict(extra="forbid")

    tool_call_id: str = Field(min_length=1, max_length=200)
    tool_name: str = Field(min_length=1, max_length=100)
    source_type: EvidenceSourceType
    source_id: str = Field(min_length=1, max_length=200)
    citation: str = Field(min_length=1, max_length=500)
    asset_code: str | None = Field(
        default=None,
        min_length=5,
        max_length=20,
        pattern=r"^[A-Z][A-Z0-9]*-\d{3}$",
    )
    payload: dict[str, Any]
