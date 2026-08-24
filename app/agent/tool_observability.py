import json
from datetime import datetime
from typing import Any

from langchain_core.messages import (
    AIMessage,
    ToolMessage,
)

from app.agent.observability import (
    DatabaseSessionFactory,
    ObservedNodeSuccess,
)
from app.agent.state import AgentState
from app.models.agent_log import AgentStep
from app.models.enums import ToolCallStatus
from app.schemas.observability import ToolCallRecordInput
from app.services.observability import record_tool_call


def _duration_ms(
    started_at: datetime,
    completed_at: datetime,
) -> int:
    return max(
        0,
        round((completed_at - started_at).total_seconds() * 1000),
    )


def _extract_tool_request(
    state: AgentState,
) -> dict[str, Any]:
    for message in reversed(state["messages"]):
        if isinstance(message, AIMessage) and message.tool_calls:
            if len(message.tool_calls) != 1:
                raise ValueError("Tool-call observability requires exactly one request.")

            request = message.tool_calls[0]
            arguments = request.get("args")

            if not isinstance(arguments, dict):
                raise ValueError("Observed tool-call arguments must be a JSON object.")

            return request

    raise ValueError("Tool-call observability could not find the model request.")


def _extract_tool_message(
    result: dict[str, object],
) -> ToolMessage:
    messages = result.get("messages")

    if not isinstance(messages, list):
        raise ValueError("Observed tool execution did not return a message list.")

    tool_messages = [message for message in messages if isinstance(message, ToolMessage)]

    if len(tool_messages) != 1:
        raise ValueError("Tool-call observability requires exactly one tool result.")

    return tool_messages[0]


def _parse_success_result(
    message: ToolMessage,
) -> dict[str, Any]:
    if not isinstance(message.content, str):
        raise ValueError("Successful tool-call content must be a JSON object string.")

    parsed_result = json.loads(message.content)

    if not isinstance(parsed_result, dict):
        raise ValueError("Successful tool-call content must decode to a JSON object.")

    return parsed_result


def create_tool_call_observer(
    session_factory: DatabaseSessionFactory,
) -> ObservedNodeSuccess:
    def observe_tool_call(
        state: AgentState,
        result: dict[str, object],
        step: AgentStep,
        started_at: datetime,
        completed_at: datetime,
    ) -> None:
        request = _extract_tool_request(
            state,
        )
        message = _extract_tool_message(
            result,
        )

        request_id = request.get("id")

        if not isinstance(request_id, str) or message.tool_call_id != request_id:
            raise ValueError("Observed tool result does not match the model request.")

        tool_name = request.get("name")
        arguments = request.get("args")

        if not isinstance(tool_name, str):
            raise ValueError("Observed tool request requires a tool name.")

        if not isinstance(arguments, dict):
            raise ValueError("Observed tool request requires JSON-object arguments.")

        is_error = getattr(message, "status", "success") == "error"

        if is_error:
            status = ToolCallStatus.FAILED
            result_json = None
            error_type = "ToolExecutionError"
            error_message = str(message.content)[:4000]
        else:
            status = ToolCallStatus.SUCCEEDED
            result_json = _parse_success_result(
                message,
            )
            error_type = None
            error_message = None

        with session_factory() as database_session:
            record_tool_call(
                database_session,
                ToolCallRecordInput(
                    run_id=state["run_id"],
                    step_id=step.id,
                    tool_name=tool_name,
                    arguments_json=arguments,
                    result_json=result_json,
                    status=status,
                    is_state_changing=False,
                    started_at=started_at,
                    completed_at=completed_at,
                    latency_ms=_duration_ms(
                        started_at,
                        completed_at,
                    ),
                    error_type=error_type,
                    error_message=error_message,
                ),
            )

    return observe_tool_call
