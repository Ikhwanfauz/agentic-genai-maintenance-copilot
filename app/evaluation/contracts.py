from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)

from app.models.enums import AgentRunStatus
from app.schemas.agent_api import AgentInvestigationStartRequest
from app.schemas.diagnosis import (
    EvidenceSourceType,
    InvestigationOutcome,
)
from app.schemas.investigation import GroundingDecision


class ScenarioCategory(StrEnum):
    NORMAL = "normal"
    DEGRADED = "degraded"
    CONTRADICTORY = "contradictory"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    ADVERSARIAL = "adversarial"


class ClaimLocation(StrEnum):
    SUMMARY = "summary"
    CONFIDENCE_RATIONALE = "confidence_rationale"
    LIKELY_CAUSES = "likely_causes"
    RECOMMENDED_ACTIONS = "recommended_actions"
    SAFETY_NOTES = "safety_notes"
    ABSTENTION_REASON = "abstention_reason"


class SafetyInvariant(StrEnum):
    NO_FABRICATED_CITATIONS = "no_fabricated_citations"
    NO_UNGROUNDED_PROPOSAL = "no_ungrounded_proposal"
    HUMAN_APPROVAL_REQUIRED = "human_approval_required"
    NO_PHYSICAL_EXECUTION = "no_physical_execution"
    BOUNDED_ITERATIONS = "bounded_iterations"


InvestigationToolName = Literal[
    "get_asset_details",
    "query_maintenance_history",
    "analyze_sensor_data",
    "search_engineering_docs",
]


class EvaluationContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ToolExpectation(EvaluationContract):
    tool_name: InvestigationToolName
    expected_arguments: dict[str, JsonValue]
    minimum_calls: int = Field(default=1, ge=0, le=10)
    maximum_calls: int = Field(default=1, ge=0, le=10)

    @model_validator(mode="after")
    def validate_call_range(self) -> Self:
        if self.maximum_calls < self.minimum_calls:
            raise ValueError("Maximum tool calls must not be lower than minimum calls.")

        return self


class ClaimExpectation(EvaluationContract):
    claim_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    location: ClaimLocation
    required_concepts: list[str] = Field(
        min_length=1,
        max_length=10,
    )
    citation_required: bool = True
    supporting_citations: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    @model_validator(mode="after")
    def validate_citation_requirement(self) -> Self:
        if self.citation_required and not self.supporting_citations:
            raise ValueError("A citation-required claim must declare supporting citations.")

        return self


class ExpectedScenarioResult(EvaluationContract):
    terminal_status: AgentRunStatus
    investigation_outcome: InvestigationOutcome
    grounding_decision: GroundingDecision

    required_tools: list[ToolExpectation] = Field(
        default_factory=list,
        max_length=10,
    )
    forbidden_tools: list[InvestigationToolName] = Field(
        default_factory=list,
        max_length=4,
    )

    required_evidence_sources: list[EvidenceSourceType] = Field(
        default_factory=list,
        max_length=4,
    )
    required_citations: list[str] = Field(
        default_factory=list,
        max_length=20,
    )
    required_claims: list[ClaimExpectation] = Field(
        default_factory=list,
        max_length=20,
    )
    forbidden_claim_concepts: list[str] = Field(
        default_factory=list,
        max_length=20,
    )

    proposal_expected: bool
    approval_pause_expected: bool
    safety_invariants: list[SafetyInvariant] = Field(
        min_length=1,
        max_length=5,
    )

    @model_validator(mode="after")
    def validate_expected_result(self) -> Self:
        required_tool_names = {expectation.tool_name for expectation in self.required_tools}
        forbidden_tool_names = set(self.forbidden_tools)

        if required_tool_names & forbidden_tool_names:
            raise ValueError("A tool must not be both required and forbidden.")

        if self.approval_pause_expected and not self.proposal_expected:
            raise ValueError("An approval pause requires an expected proposal.")

        if self.proposal_expected:
            if self.investigation_outcome != InvestigationOutcome.DIAGNOSIS:
                raise ValueError("A proposal requires an expected diagnosis outcome.")

            if self.grounding_decision != GroundingDecision.GROUNDED:
                raise ValueError("A proposal requires an expected grounded decision.")

        expected_status_by_outcome = {
            InvestigationOutcome.INSUFFICIENT_EVIDENCE: AgentRunStatus.ABSTAINED,
            InvestigationOutcome.OUT_OF_SCOPE: AgentRunStatus.COMPLETED,
        }
        required_status = expected_status_by_outcome.get(self.investigation_outcome)

        if required_status is not None and self.terminal_status != required_status:
            raise ValueError("The terminal status must match the expected investigation outcome.")

        expected_grounding_by_outcome = {
            InvestigationOutcome.DIAGNOSIS: GroundingDecision.GROUNDED,
            InvestigationOutcome.INSUFFICIENT_EVIDENCE: (GroundingDecision.ABSTAINED),
            InvestigationOutcome.OUT_OF_SCOPE: GroundingDecision.OUT_OF_SCOPE,
        }

        if self.grounding_decision != expected_grounding_by_outcome[self.investigation_outcome]:
            raise ValueError("The grounding decision must match the investigation outcome.")

        expected_citations = set(self.required_citations)

        for claim in self.required_claims:
            unsupported_citations = set(claim.supporting_citations) - expected_citations

            if unsupported_citations:
                raise ValueError("Claim-support citations must be declared as required citations.")

        return self


class EvaluationScenario(EvaluationContract):
    scenario_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^v7\.[a-z0-9][a-z0-9._-]*$",
    )
    scenario_version: int = Field(default=1, gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    category: ScenarioCategory
    fixture_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9._-]*$",
    )
    request: AgentInvestigationStartRequest
    expected: ExpectedScenarioResult
    rationale: str = Field(min_length=1, max_length=2000)


class EvaluationDataset(EvaluationContract):
    dataset_id: str = Field(
        min_length=1,
        max_length=100,
        pattern=r"^v7\.[a-z0-9][a-z0-9._-]*$",
    )
    dataset_version: int = Field(gt=0)
    description: str = Field(min_length=1, max_length=2000)
    required_categories: list[ScenarioCategory] = Field(
        min_length=1,
        max_length=5,
    )
    scenarios: list[EvaluationScenario] = Field(
        min_length=1,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_dataset(self) -> Self:
        scenario_ids = [scenario.scenario_id for scenario in self.scenarios]

        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("Evaluation scenario IDs must be unique.")

        if len(self.required_categories) != len(set(self.required_categories)):
            raise ValueError("Required scenario categories must be unique.")

        present_categories = {scenario.category for scenario in self.scenarios}
        missing_categories = [
            category for category in self.required_categories if category not in present_categories
        ]

        if missing_categories:
            missing_names = ", ".join(category.value for category in missing_categories)
            raise ValueError(f"Evaluation dataset is missing required categories: {missing_names}.")

        return self
