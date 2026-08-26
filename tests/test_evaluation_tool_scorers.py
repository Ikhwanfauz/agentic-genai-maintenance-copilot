from datetime import UTC, datetime

from app.evaluation.contracts import ToolExpectation
from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricStatus,
)
from app.evaluation.scorers.tools import (
    score_tool_arguments,
    score_tool_selection,
)
from app.models.enums import ToolCallStatus
from app.schemas.observability import ToolCallRecordInput

OBSERVED_AT = datetime(
    2026,
    8,
    27,
    tzinfo=UTC,
)


def create_tool_call(
    tool_name: str,
    arguments: dict[str, object] | None = None,
) -> ToolCallRecordInput:
    return ToolCallRecordInput(
        run_id="evaluation-run",
        tool_name=tool_name,
        arguments_json=arguments or {},
        result_json={"fixture": True},
        status=ToolCallStatus.SUCCEEDED,
        started_at=OBSERVED_AT,
        completed_at=OBSERVED_AT,
        latency_ms=0,
    )


def create_tool_expectation(
    *,
    minimum_calls: int = 1,
    maximum_calls: int = 1,
) -> ToolExpectation:
    return ToolExpectation(
        tool_name="get_asset_details",
        expected_arguments={"asset_code": "P-101"},
        minimum_calls=minimum_calls,
        maximum_calls=maximum_calls,
    )


def test_tool_selection_passes_with_expected_call_count() -> None:
    result = score_tool_selection(
        required_tools=[
            create_tool_expectation(
                minimum_calls=1,
                maximum_calls=2,
            )
        ],
        forbidden_tools=[],
        tool_calls=[
            create_tool_call("get_asset_details"),
            create_tool_call("get_asset_details"),
        ],
    )

    assert result.metric == EvaluationMetric.TOOL_SELECTION
    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.actual == {
        "call_counts": {
            "get_asset_details": 2,
        }
    }


def test_tool_selection_fails_when_required_tool_is_missing() -> None:
    result = score_tool_selection(
        required_tools=[create_tool_expectation()],
        forbidden_tools=[],
        tool_calls=[],
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.details == [
        "Tool 'get_asset_details' required at least 1 call(s) but received 0."
    ]


def test_tool_selection_fails_when_maximum_calls_are_exceeded() -> None:
    result = score_tool_selection(
        required_tools=[create_tool_expectation()],
        forbidden_tools=[],
        tool_calls=[
            create_tool_call("get_asset_details"),
            create_tool_call("get_asset_details"),
        ],
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.details == ["Tool 'get_asset_details' allowed at most 1 call(s) but received 2."]


def test_tool_selection_fails_when_forbidden_tool_is_called() -> None:
    result = score_tool_selection(
        required_tools=[],
        forbidden_tools=["search_engineering_docs"],
        tool_calls=[
            create_tool_call("search_engineering_docs"),
        ],
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.details == ["Forbidden tool 'search_engineering_docs' was called 1 time(s)."]


def test_tool_selection_passes_when_no_tools_are_expected_or_called() -> None:
    result = score_tool_selection(
        required_tools=[],
        forbidden_tools=[
            "get_asset_details",
            "query_maintenance_history",
            "analyze_sensor_data",
            "search_engineering_docs",
        ],
        tool_calls=[],
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.actual == {"call_counts": {}}


def test_tool_arguments_pass_for_exact_match() -> None:
    result = score_tool_arguments(
        required_tools=[create_tool_expectation()],
        tool_calls=[
            create_tool_call(
                "get_asset_details",
                {"asset_code": "P-101"},
            )
        ],
    )

    assert result.metric == EvaluationMetric.TOOL_ARGUMENTS
    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
    assert result.actual == {
        "arguments_by_tool": {
            "get_asset_details": [
                {"asset_code": "P-101"},
            ]
        }
    }


def test_tool_arguments_fail_for_wrong_value() -> None:
    result = score_tool_arguments(
        required_tools=[create_tool_expectation()],
        tool_calls=[
            create_tool_call(
                "get_asset_details",
                {"asset_code": "P-201"},
            )
        ],
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.score == 0.0
    assert result.details == [
        "Tool 'get_asset_details' call 1 expected arguments "
        '{"asset_code":"P-101"} but received '
        '{"asset_code":"P-201"}.'
    ]


def test_tool_arguments_fail_when_argument_is_missing() -> None:
    result = score_tool_arguments(
        required_tools=[create_tool_expectation()],
        tool_calls=[
            create_tool_call(
                "get_asset_details",
                {},
            )
        ],
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.details == [
        "Tool 'get_asset_details' call 1 expected arguments "
        '{"asset_code":"P-101"} but received {}.'
    ]


def test_tool_arguments_fail_for_unexpected_extra_argument() -> None:
    result = score_tool_arguments(
        required_tools=[create_tool_expectation()],
        tool_calls=[
            create_tool_call(
                "get_asset_details",
                {
                    "asset_code": "P-101",
                    "unsafe_override": True,
                },
            )
        ],
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.details == [
        "Tool 'get_asset_details' call 1 expected arguments "
        '{"asset_code":"P-101"} but received '
        '{"asset_code":"P-101","unsafe_override":true}.'
    ]


def test_tool_arguments_fail_when_required_call_is_missing() -> None:
    result = score_tool_arguments(
        required_tools=[create_tool_expectation()],
        tool_calls=[],
    )

    assert result.status == EvaluationMetricStatus.FAILED
    assert result.details == [
        "No call was available to validate required arguments for tool 'get_asset_details'."
    ]


def test_tool_arguments_allow_absent_optional_call() -> None:
    result = score_tool_arguments(
        required_tools=[
            create_tool_expectation(
                minimum_calls=0,
                maximum_calls=1,
            )
        ],
        tool_calls=[],
    )

    assert result.status == EvaluationMetricStatus.PASSED
    assert result.score == 1.0
