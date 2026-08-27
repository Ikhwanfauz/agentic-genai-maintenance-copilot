import pytest
from langchain_core.messages import (
    HumanMessage,
    ToolMessage,
)

from app.agent.grounding import build_grounding_context_message
from app.agent.policy import evaluate_evidence_coverage
from app.evaluation.fixture_registry import get_fixture_plan
from app.evaluation.scripted_models import (
    ScriptedDiagnosisModel,
    ScriptedInvestigationModel,
)
from app.schemas.diagnosis import (
    EvidenceSourceType,
    MaintenanceDiagnosis,
)
from app.schemas.evidence import CollectedEvidence


def create_p101_evidence_ledger() -> list[CollectedEvidence]:
    evidence_details = [
        (
            EvidenceSourceType.ASSET_DETAILS,
            "P-101",
            "asset:P-101",
        ),
        (
            EvidenceSourceType.MAINTENANCE_HISTORY,
            "3",
            "maintenance_record:3",
        ),
        (
            EvidenceSourceType.SENSOR_ANALYSIS,
            "P-101:vibration",
            "sensor:P-101:vibration",
        ),
        (
            EvidenceSourceType.ENGINEERING_DOCUMENT,
            "ENG-PUMP-001:elevated-vibration",
            ("ENG-PUMP-001 | Elevated Vibration | pump_troubleshooting_guide.md"),
        ),
    ]

    return [
        CollectedEvidence(
            tool_call_id=f"scripted-call-{index}",
            tool_name="evaluation_fixture",
            source_type=source_type,
            source_id=source_id,
            citation=citation,
            asset_code="P-101",
            payload={"source_id": source_id},
        )
        for index, (
            source_type,
            source_id,
            citation,
        ) in enumerate(
            evidence_details,
            start=1,
        )
    ]


def create_grounding_message():
    ledger = create_p101_evidence_ledger()
    coverage = evaluate_evidence_coverage(
        ledger,
        "P-101",
    )

    return build_grounding_context_message(
        ledger,
        coverage,
        "P-101",
    )


def test_scripted_investigation_model_replays_tool_calls_in_order() -> None:
    fixture = get_fixture_plan("p101-grounded-monitoring")
    model = ScriptedInvestigationModel(fixture)
    messages = [
        HumanMessage(content="Investigate P-101."),
    ]

    for expected_call in fixture.tool_calls:
        response = model.invoke(messages)
        actual_call = response.tool_calls[0]

        assert actual_call["name"] == expected_call.tool_name
        assert actual_call["args"] == expected_call.arguments
        assert actual_call["id"] == expected_call.call_id

        messages.extend(
            [
                response,
                ToolMessage(
                    content="{}",
                    tool_call_id=expected_call.call_id,
                    name=expected_call.tool_name,
                ),
            ]
        )


def test_scripted_investigation_model_completes_after_final_tool() -> None:
    fixture = get_fixture_plan("p101-grounded-monitoring")
    model = ScriptedInvestigationModel(fixture)
    messages = [
        HumanMessage(content="Investigate P-101."),
    ]

    for scripted_call in fixture.tool_calls:
        response = model.invoke(messages)
        messages.extend(
            [
                response,
                ToolMessage(
                    content="{}",
                    tool_call_id=scripted_call.call_id,
                    name=scripted_call.tool_name,
                ),
            ]
        )

    completion = model.invoke(messages)

    assert completion.tool_calls == []
    assert completion.content == fixture.completion_message


def test_scripted_investigation_model_completes_without_tools() -> None:
    fixture = get_fixture_plan("p101-direct-machinery-control")
    model = ScriptedInvestigationModel(fixture)

    response = model.invoke([HumanMessage(content="Stop P-101 and change the PLC parameter.")])

    assert response.tool_calls == []
    assert response.content == fixture.completion_message


def test_scripted_diagnosis_uses_only_allowlisted_evidence() -> None:
    fixture = get_fixture_plan("p101-grounded-monitoring")
    model = ScriptedDiagnosisModel(fixture)

    diagnosis = model.invoke([create_grounding_message()])

    assert isinstance(diagnosis, MaintenanceDiagnosis)
    assert diagnosis.outcome == fixture.diagnosis.outcome
    assert {reference.citation for reference in diagnosis.evidence} == set(
        fixture.diagnosis.evidence_citations
    )


def test_scripted_diagnosis_rejects_citation_outside_allowlist() -> None:
    fixture = get_fixture_plan("p101-grounded-monitoring")
    fixture.diagnosis.evidence_citations.append("sensor:P-101:invented")
    model = ScriptedDiagnosisModel(fixture)

    with pytest.raises(
        ValueError,
        match="is not in the grounding allowlist",
    ):
        model.invoke([create_grounding_message()])


def test_scripted_diagnosis_requires_grounding_metadata() -> None:
    fixture = get_fixture_plan("p101-grounded-monitoring")
    model = ScriptedDiagnosisModel(fixture)

    with pytest.raises(
        ValueError,
        match="requires application-owned grounding metadata",
    ):
        model.invoke(
            [
                HumanMessage(content="No grounding metadata supplied."),
            ]
        )
