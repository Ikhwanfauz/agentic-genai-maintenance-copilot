import json
from collections import Counter
from collections.abc import Sequence

from app.evaluation.contracts import (
    InvestigationToolName,
    ToolExpectation,
)
from app.evaluation.results import (
    EvaluationMetric,
    EvaluationMetricResult,
    create_binary_metric_result,
)
from app.schemas.observability import ToolCallRecordInput


def score_tool_selection(
    required_tools: Sequence[ToolExpectation],
    forbidden_tools: Sequence[InvestigationToolName],
    tool_calls: Sequence[ToolCallRecordInput],
) -> EvaluationMetricResult:
    call_counts = Counter(tool_call.tool_name for tool_call in tool_calls)
    failure_details: list[str] = []

    for expectation in required_tools:
        actual_count = call_counts[expectation.tool_name]

        if actual_count < expectation.minimum_calls:
            failure_details.append(
                f"Tool '{expectation.tool_name}' required at least "
                f"{expectation.minimum_calls} call(s) but received "
                f"{actual_count}."
            )

        if actual_count > expectation.maximum_calls:
            failure_details.append(
                f"Tool '{expectation.tool_name}' allowed at most "
                f"{expectation.maximum_calls} call(s) but received "
                f"{actual_count}."
            )

    for tool_name in sorted(set(forbidden_tools)):
        actual_count = call_counts[tool_name]

        if actual_count:
            failure_details.append(
                f"Forbidden tool '{tool_name}' was called {actual_count} time(s)."
            )

    passed = not failure_details

    return create_binary_metric_result(
        EvaluationMetric.TOOL_SELECTION,
        passed,
        summary=(
            "Tool selection matched the scenario expectations."
            if passed
            else "Tool selection violated the scenario expectations."
        ),
        expected={
            "required_tools": [
                expectation.model_dump(mode="json") for expectation in required_tools
            ],
            "forbidden_tools": sorted(set(forbidden_tools)),
        },
        actual={
            "call_counts": dict(sorted(call_counts.items())),
        },
        failure_details=failure_details,
    )


def _display_arguments(
    arguments: dict[str, object],
) -> str:
    return json.dumps(
        arguments,
        sort_keys=True,
        separators=(",", ":"),
    )


def score_tool_arguments(
    required_tools: Sequence[ToolExpectation],
    tool_calls: Sequence[ToolCallRecordInput],
) -> EvaluationMetricResult:
    failure_details: list[str] = []

    for expectation in required_tools:
        matching_tool_calls = [
            tool_call for tool_call in tool_calls if tool_call.tool_name == expectation.tool_name
        ]

        if expectation.minimum_calls > 0 and not matching_tool_calls:
            failure_details.append(
                "No call was available to validate required arguments "
                f"for tool '{expectation.tool_name}'."
            )
            continue

        for call_number, tool_call in enumerate(
            matching_tool_calls,
            start=1,
        ):
            if tool_call.arguments_json != expectation.expected_arguments:
                failure_details.append(
                    f"Tool '{expectation.tool_name}' call "
                    f"{call_number} expected arguments "
                    f"{_display_arguments(expectation.expected_arguments)} "
                    "but received "
                    f"{_display_arguments(tool_call.arguments_json)}."
                )

    arguments_by_tool: dict[str, list[dict[str, object]]] = {}

    for tool_call in tool_calls:
        arguments_by_tool.setdefault(
            tool_call.tool_name,
            [],
        ).append(dict(tool_call.arguments_json))

    passed = not failure_details

    return create_binary_metric_result(
        EvaluationMetric.TOOL_ARGUMENTS,
        passed,
        summary=(
            "Tool arguments matched the scenario expectations."
            if passed
            else "Tool arguments violated the scenario expectations."
        ),
        expected={
            "required_arguments": [
                {
                    "tool_name": expectation.tool_name,
                    "arguments": expectation.expected_arguments,
                }
                for expectation in required_tools
            ]
        },
        actual={
            "arguments_by_tool": {
                tool_name: arguments_by_tool[tool_name] for tool_name in sorted(arguments_by_tool)
            }
        },
        failure_details=failure_details,
    )
