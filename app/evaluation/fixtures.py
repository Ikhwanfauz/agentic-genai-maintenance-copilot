from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from app.evaluation.contracts import InvestigationToolName
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    InvestigationOutcome,
    RecommendedAction,
)


class EvaluationFixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FixtureMutationType(StrEnum):
    EMPTY_ENGINEERING_DOCUMENTS = "empty_engineering_documents"
    LIMITED_MAINTENANCE_HISTORY = "limited_maintenance_history"
    EMPTY_SENSOR_DATA = "empty_sensor_data"
    EMPTY_MAINTENANCE_HISTORY = "empty_maintenance_history"


class EvaluationFixtureMutation(EvaluationFixtureModel):
    mutation_type: FixtureMutationType
    asset_code: str | None = Field(
        default=None,
        min_length=5,
        max_length=20,
        pattern=r"^[A-Z][A-Z0-9]*-\d{3}$",
    )
    retained_maintenance_record_ids: list[int] = Field(
        default_factory=list,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_mutation_configuration(self) -> Self:
        record_ids = self.retained_maintenance_record_ids

        if any(record_id <= 0 for record_id in record_ids):
            raise ValueError("Retained maintenance-record IDs must be positive.")

        if len(record_ids) != len(set(record_ids)):
            raise ValueError("Retained maintenance-record IDs must be unique.")

        asset_scoped_mutations = {
            FixtureMutationType.LIMITED_MAINTENANCE_HISTORY,
            FixtureMutationType.EMPTY_SENSOR_DATA,
            FixtureMutationType.EMPTY_MAINTENANCE_HISTORY,
        }

        if self.mutation_type in asset_scoped_mutations and self.asset_code is None:
            raise ValueError("The selected fixture mutation requires an asset code.")

        if (
            self.mutation_type == FixtureMutationType.EMPTY_ENGINEERING_DOCUMENTS
            and self.asset_code is not None
        ):
            raise ValueError(
                "Empty engineering-document mutation is "
                "collection-scoped and must not declare an asset."
            )

        if self.mutation_type == FixtureMutationType.LIMITED_MAINTENANCE_HISTORY and not record_ids:
            raise ValueError("Limited maintenance history requires retained record IDs.")

        if self.mutation_type != FixtureMutationType.LIMITED_MAINTENANCE_HISTORY and record_ids:
            raise ValueError("Only limited maintenance history may declare retained record IDs.")

        return self


class ScriptedToolCall(EvaluationFixtureModel):
    call_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    tool_name: InvestigationToolName
    arguments: dict[str, JsonValue]


class ScriptedDiagnosisPlan(EvaluationFixtureModel):
    asset_code: str | None = Field(
        default=None,
        min_length=5,
        max_length=20,
        pattern=r"^[A-Z][A-Z0-9]*-\d{3}$",
    )
    outcome: InvestigationOutcome
    summary: str = Field(
        min_length=1,
        max_length=2000,
    )
    confidence: DiagnosisConfidence
    confidence_rationale: str = Field(
        min_length=1,
        max_length=1000,
    )
    likely_causes: list[str] = Field(
        default_factory=list,
        max_length=5,
    )
    evidence_citations: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    recommended_actions: list[RecommendedAction] = Field(
        default_factory=list,
        max_length=10,
    )
    safety_notes: list[str] = Field(
        min_length=1,
        max_length=10,
    )
    abstention_reason: str | None = Field(
        default=None,
        min_length=1,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_diagnosis_plan(self) -> Self:
        if len(self.evidence_citations) != len(set(self.evidence_citations)):
            raise ValueError("Scripted diagnosis citations must be unique.")

        if self.outcome == InvestigationOutcome.DIAGNOSIS:
            if not self.likely_causes:
                raise ValueError("A scripted diagnosis requires likely causes.")

            if not self.evidence_citations:
                raise ValueError("A scripted diagnosis requires evidence citations.")

            if self.abstention_reason is not None:
                raise ValueError("A scripted diagnosis must not contain an abstention reason.")

            return self

        if self.abstention_reason is None:
            raise ValueError("A scripted non-diagnosis requires an abstention reason.")

        if self.confidence != DiagnosisConfidence.LOW:
            raise ValueError("A scripted non-diagnosis must use low confidence.")

        if self.likely_causes:
            raise ValueError("A scripted non-diagnosis must not contain likely causes.")

        if self.evidence_citations:
            raise ValueError("A scripted non-diagnosis must not contain evidence citations.")

        if self.recommended_actions:
            raise ValueError("A scripted non-diagnosis must not contain recommended actions.")

        return self


class ScenarioFixturePlan(EvaluationFixtureModel):
    fixture_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    mutations: list[EvaluationFixtureMutation] = Field(
        default_factory=list,
        max_length=10,
    )
    tool_calls: list[ScriptedToolCall] = Field(
        default_factory=list,
        max_length=10,
    )
    completion_message: str = Field(
        min_length=1,
        max_length=1000,
    )
    diagnosis: ScriptedDiagnosisPlan

    @model_validator(mode="after")
    def validate_fixture_plan(self) -> Self:
        call_ids = [tool_call.call_id for tool_call in self.tool_calls]

        if len(call_ids) != len(set(call_ids)):
            raise ValueError("Scripted tool-call IDs must be unique.")

        mutation_targets = [
            (
                mutation.mutation_type,
                mutation.asset_code,
            )
            for mutation in self.mutations
        ]

        if len(mutation_targets) != len(set(mutation_targets)):
            raise ValueError("Fixture mutation type and asset combinations must be unique.")

        return self
