from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage

from app.agent.observability import (
    DatabaseSessionFactory,
    ObservedNodeFailure,
    ObservedNodeSuccess,
)
from app.agent.state import AgentState
from app.models.agent_log import AgentStep
from app.schemas.observability import (
    ModelUsageRecordInput,
)
from app.services.observability import (
    record_model_usage,
)


def _extract_ai_message(
    result: dict[str, object],
) -> AIMessage | None:
    messages = result.get("messages")

    if messages is None:
        return None

    if not isinstance(messages, list):
        raise ValueError("Observed model result messages must be a list.")

    ai_messages = [message for message in messages if isinstance(message, AIMessage)]

    if len(ai_messages) > 1:
        raise ValueError("Observed model result contains multiple AI messages.")

    return ai_messages[0] if ai_messages else None


def _read_token_count(
    usage_metadata: dict[str, Any],
    key: str,
) -> int:
    value = usage_metadata.get(
        key,
        0,
    )

    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"Observed model usage '{key}' must be a non-negative integer.")

    return value


def create_model_usage_observer(
    session_factory: DatabaseSessionFactory,
    *,
    count_without_message: bool = False,
) -> ObservedNodeSuccess:
    def observe_model_usage(
        state: AgentState,
        result: dict[str, object],
        _step: AgentStep,
        _started_at: datetime,
        _completed_at: datetime,
    ) -> None:
        message = _extract_ai_message(
            result,
        )

        if message is None and not count_without_message:
            return

        usage_metadata = message.usage_metadata if message is not None else None

        if usage_metadata is None:
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
        else:
            prompt_tokens = _read_token_count(
                usage_metadata,
                "input_tokens",
            )
            completion_tokens = _read_token_count(
                usage_metadata,
                "output_tokens",
            )
            total_tokens = _read_token_count(
                usage_metadata,
                "total_tokens",
            )

        with session_factory() as database_session:
            record_model_usage(
                database_session,
                ModelUsageRecordInput(
                    run_id=state["run_id"],
                    model_calls=1,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                ),
            )

    return observe_model_usage


def create_failed_model_usage_observer(
    session_factory: DatabaseSessionFactory,
) -> ObservedNodeFailure:
    def observe_failed_model_usage(
        state: AgentState,
        _error: Exception,
        _step: AgentStep,
        _started_at: datetime,
        _completed_at: datetime,
    ) -> None:
        with session_factory() as database_session:
            record_model_usage(
                database_session,
                ModelUsageRecordInput(
                    run_id=state["run_id"],
                ),
            )

    return observe_failed_model_usage
