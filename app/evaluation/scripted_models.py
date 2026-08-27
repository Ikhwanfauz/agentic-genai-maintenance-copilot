import json
from collections.abc import Sequence

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    SystemMessage,
    ToolMessage,
)

from app.evaluation.fixtures import ScenarioFixturePlan
from app.schemas.diagnosis import (
    EvidenceReference,
    EvidenceSourceType,
    MaintenanceDiagnosis,
)

_GROUNDING_METADATA_PREFIX = "Application-owned grounding metadata"


def _load_grounding_metadata(
    messages: Sequence[BaseMessage],
) -> dict[str, object]:
    grounding_message = next(
        (
            message
            for message in messages
            if isinstance(message, SystemMessage)
            and isinstance(message.content, str)
            and message.content.startswith(_GROUNDING_METADATA_PREFIX)
        ),
        None,
    )

    if grounding_message is None:
        raise ValueError("Scripted diagnosis requires application-owned grounding metadata.")

    try:
        serialized_metadata = grounding_message.content.split(
            "\n",
            maxsplit=1,
        )[1]
    except IndexError as error:
        raise ValueError("Application-owned grounding metadata is malformed.") from error

    metadata = json.loads(serialized_metadata)

    if not isinstance(metadata, dict):
        raise ValueError("Application-owned grounding metadata must be a JSON object.")

    return metadata


def _create_evidence_references(
    fixture: ScenarioFixturePlan,
    metadata: dict[str, object],
) -> list[EvidenceReference]:
    raw_allowlist = metadata.get("citation_allowlist")

    if not isinstance(raw_allowlist, list):
        raise ValueError("Application-owned grounding metadata requires a citation allowlist.")

    entries_by_citation: dict[str, dict[str, object]] = {}

    for raw_entry in raw_allowlist:
        if not isinstance(raw_entry, dict):
            raise ValueError("Every citation allowlist entry must be an object.")

        citation = raw_entry.get("citation")

        if not isinstance(citation, str):
            raise ValueError("Every citation allowlist entry requires a citation string.")

        entries_by_citation[citation] = raw_entry

    references: list[EvidenceReference] = []

    for citation in fixture.diagnosis.evidence_citations:
        try:
            entry = entries_by_citation[citation]
        except KeyError as error:
            raise ValueError(
                f"Scripted citation '{citation}' is not in the grounding allowlist."
            ) from error

        source_type = entry.get("source_type")
        source_id = entry.get("source_id")

        if not isinstance(source_type, str) or not isinstance(source_id, str):
            raise ValueError("Citation allowlist entries require string source metadata.")

        references.append(
            EvidenceReference(
                source_type=EvidenceSourceType(source_type),
                source_id=source_id,
                summary=f"Scripted {source_type} evidence.",
                citation=citation,
            )
        )

    return references


class ScriptedInvestigationModel:
    """Replay one deterministic tool-selection plan."""

    def __init__(self, fixture: ScenarioFixturePlan) -> None:
        self._fixture = fixture.model_copy(deep=True)

    def invoke(
        self,
        messages: Sequence[BaseMessage],
        config: object | None = None,
        **kwargs: object,
    ) -> AIMessage:
        del config, kwargs

        completed_tool_calls = sum(isinstance(message, ToolMessage) for message in messages)

        if completed_tool_calls > len(self._fixture.tool_calls):
            raise RuntimeError("Observed more tool results than the scripted fixture declares.")

        if completed_tool_calls == len(self._fixture.tool_calls):
            return AIMessage(content=self._fixture.completion_message)

        scripted_call = self._fixture.tool_calls[completed_tool_calls]

        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": scripted_call.tool_name,
                    "args": scripted_call.arguments,
                    "id": scripted_call.call_id,
                    "type": "tool_call",
                }
            ],
        )


class ScriptedDiagnosisModel:
    """Create one structured diagnosis from trusted grounding metadata."""

    def __init__(self, fixture: ScenarioFixturePlan) -> None:
        self._fixture = fixture.model_copy(deep=True)

    def invoke(
        self,
        messages: Sequence[BaseMessage],
        config: object | None = None,
        **kwargs: object,
    ) -> MaintenanceDiagnosis:
        del config, kwargs

        metadata = _load_grounding_metadata(messages)
        plan = self._fixture.diagnosis

        return MaintenanceDiagnosis(
            asset_code=plan.asset_code,
            outcome=plan.outcome,
            summary=plan.summary,
            confidence=plan.confidence,
            confidence_rationale=plan.confidence_rationale,
            likely_causes=list(plan.likely_causes),
            evidence=_create_evidence_references(
                self._fixture,
                metadata,
            ),
            recommended_actions=[
                action.model_copy(deep=True) for action in plan.recommended_actions
            ],
            safety_notes=list(plan.safety_notes),
            abstention_reason=plan.abstention_reason,
        )
