import pytest
from pydantic import ValidationError

from app.evaluation.fixtures import (
    EvaluationFixtureMutation,
    FixtureMutationType,
    ScenarioFixturePlan,
    ScriptedDiagnosisPlan,
    ScriptedToolCall,
)
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    InvestigationOutcome,
)


def test_scripted_tool_call_round_trips_through_json() -> None:
    tool_call = ScriptedToolCall(
        call_id="asset-call-1",
        tool_name="get_asset_details",
        arguments={"asset_code": "P-101"},
    )

    restored = ScriptedToolCall.model_validate_json(tool_call.model_dump_json())

    assert restored == tool_call


def test_scripted_tool_call_rejects_unknown_fields() -> None:
    with pytest.raises(
        ValidationError,
        match="Extra inputs are not permitted",
    ):
        ScriptedToolCall(
            call_id="asset-call-1",
            tool_name="get_asset_details",
            arguments={"asset_code": "P-101"},
            bypass_safety=True,
        )


def test_empty_engineering_documents_is_collection_scoped() -> None:
    mutation = EvaluationFixtureMutation(
        mutation_type=(FixtureMutationType.EMPTY_ENGINEERING_DOCUMENTS)
    )

    assert mutation.asset_code is None
    assert mutation.retained_maintenance_record_ids == []


def test_empty_engineering_documents_rejects_asset_scope() -> None:
    with pytest.raises(
        ValidationError,
        match="must not declare an asset",
    ):
        EvaluationFixtureMutation(
            mutation_type=(FixtureMutationType.EMPTY_ENGINEERING_DOCUMENTS),
            asset_code="P-101",
        )


@pytest.mark.parametrize(
    "mutation_type",
    [
        FixtureMutationType.EMPTY_SENSOR_DATA,
        FixtureMutationType.EMPTY_MAINTENANCE_HISTORY,
    ],
)
def test_asset_data_mutation_requires_asset_code(
    mutation_type: FixtureMutationType,
) -> None:
    with pytest.raises(
        ValidationError,
        match="requires an asset code",
    ):
        EvaluationFixtureMutation(
            mutation_type=mutation_type,
        )


def test_limited_history_requires_retained_records() -> None:
    with pytest.raises(
        ValidationError,
        match="requires retained record IDs",
    ):
        EvaluationFixtureMutation(
            mutation_type=(FixtureMutationType.LIMITED_MAINTENANCE_HISTORY),
            asset_code="P-101",
        )


def test_limited_history_accepts_unique_positive_records() -> None:
    mutation = EvaluationFixtureMutation(
        mutation_type=(FixtureMutationType.LIMITED_MAINTENANCE_HISTORY),
        asset_code="P-101",
        retained_maintenance_record_ids=[3],
    )

    assert mutation.asset_code == "P-101"
    assert mutation.retained_maintenance_record_ids == [3]


@pytest.mark.parametrize(
    "record_ids",
    [
        [0],
        [-1],
    ],
)
def test_retained_record_ids_must_be_positive(
    record_ids: list[int],
) -> None:
    with pytest.raises(
        ValidationError,
        match="must be positive",
    ):
        EvaluationFixtureMutation(
            mutation_type=(FixtureMutationType.LIMITED_MAINTENANCE_HISTORY),
            asset_code="P-101",
            retained_maintenance_record_ids=record_ids,
        )


def test_retained_record_ids_must_be_unique() -> None:
    with pytest.raises(
        ValidationError,
        match="must be unique",
    ):
        EvaluationFixtureMutation(
            mutation_type=(FixtureMutationType.LIMITED_MAINTENANCE_HISTORY),
            asset_code="P-101",
            retained_maintenance_record_ids=[3, 3],
        )


def create_diagnosis_plan(
    *,
    outcome: InvestigationOutcome = (InvestigationOutcome.DIAGNOSIS),
) -> ScriptedDiagnosisPlan:
    if outcome == InvestigationOutcome.DIAGNOSIS:
        return ScriptedDiagnosisPlan(
            asset_code="P-101",
            outcome=outcome,
            summary="P-101 has an increasing vibration condition.",
            confidence=DiagnosisConfidence.MEDIUM,
            confidence_rationale=("Multiple deterministic evidence sources agree."),
            likely_causes=["Possible coupling alignment condition"],
            evidence_citations=["asset:P-101"],
            safety_notes=["Human review is required before physical work."],
        )

    return ScriptedDiagnosisPlan(
        asset_code=None,
        outcome=outcome,
        summary="The request cannot be diagnosed safely.",
        confidence=DiagnosisConfidence.LOW,
        confidence_rationale=("Required evidence or application scope is missing."),
        safety_notes=["No physical maintenance action was performed."],
        abstention_reason=("The investigation cannot produce a grounded diagnosis."),
    )


def test_scripted_diagnosis_plan_round_trips_through_json() -> None:
    plan = create_diagnosis_plan()

    restored = ScriptedDiagnosisPlan.model_validate_json(plan.model_dump_json())

    assert restored == plan


def test_scripted_diagnosis_requires_evidence_citations() -> None:
    payload = {
        **create_diagnosis_plan().model_dump(mode="python"),
        "evidence_citations": [],
    }

    with pytest.raises(
        ValidationError,
        match="requires evidence citations",
    ):
        ScriptedDiagnosisPlan.model_validate(payload)


def test_scripted_non_diagnosis_requires_abstention_reason() -> None:
    payload = {
        **create_diagnosis_plan(outcome=InvestigationOutcome.OUT_OF_SCOPE).model_dump(
            mode="python"
        ),
        "abstention_reason": None,
    }

    with pytest.raises(
        ValidationError,
        match="requires an abstention reason",
    ):
        ScriptedDiagnosisPlan.model_validate(payload)


def test_scripted_non_diagnosis_requires_low_confidence() -> None:
    payload = {
        **create_diagnosis_plan(outcome=InvestigationOutcome.OUT_OF_SCOPE).model_dump(
            mode="python"
        ),
        "confidence": DiagnosisConfidence.MEDIUM,
    }

    with pytest.raises(
        ValidationError,
        match="must use low confidence",
    ):
        ScriptedDiagnosisPlan.model_validate(payload)


def test_scripted_non_diagnosis_rejects_evidence_citations() -> None:
    payload = {
        **create_diagnosis_plan(outcome=InvestigationOutcome.OUT_OF_SCOPE).model_dump(
            mode="python"
        ),
        "evidence_citations": ["asset:P-101"],
    }

    with pytest.raises(
        ValidationError,
        match="must not contain evidence citations",
    ):
        ScriptedDiagnosisPlan.model_validate(payload)


def test_scenario_fixture_plan_accepts_complete_script() -> None:
    plan = ScenarioFixturePlan(
        fixture_id="p101-grounded-test",
        mutations=[],
        tool_calls=[
            ScriptedToolCall(
                call_id="asset-call-1",
                tool_name="get_asset_details",
                arguments={"asset_code": "P-101"},
            )
        ],
        completion_message="Required evidence was collected.",
        diagnosis=create_diagnosis_plan(),
    )

    assert plan.fixture_id == "p101-grounded-test"
    assert len(plan.tool_calls) == 1
    assert plan.diagnosis.outcome == (InvestigationOutcome.DIAGNOSIS)


def test_scenario_fixture_plan_rejects_duplicate_call_ids() -> None:
    tool_call = ScriptedToolCall(
        call_id="duplicate-call",
        tool_name="get_asset_details",
        arguments={"asset_code": "P-101"},
    )

    with pytest.raises(
        ValidationError,
        match="tool-call IDs must be unique",
    ):
        ScenarioFixturePlan(
            fixture_id="duplicate-call-test",
            tool_calls=[
                tool_call,
                tool_call.model_copy(),
            ],
            completion_message="Duplicate calls are invalid.",
            diagnosis=create_diagnosis_plan(),
        )


def test_scenario_fixture_plan_rejects_duplicate_mutation_targets() -> None:
    mutation = EvaluationFixtureMutation(
        mutation_type=FixtureMutationType.EMPTY_SENSOR_DATA,
        asset_code="P-101",
    )

    with pytest.raises(
        ValidationError,
        match="combinations must be unique",
    ):
        ScenarioFixturePlan(
            fixture_id="duplicate-mutation-test",
            mutations=[
                mutation,
                mutation.model_copy(),
            ],
            tool_calls=[],
            completion_message="Duplicate mutations are invalid.",
            diagnosis=create_diagnosis_plan(outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE),
        )
