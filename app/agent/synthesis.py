from collections.abc import Callable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import Runnable
from pydantic import ValidationError

from app.agent.grounding import (
    build_grounding_context_message,
    enforce_grounded_diagnosis,
)
from app.agent.prompts import DIAGNOSIS_SYNTHESIS_PROMPT
from app.agent.state import AgentRoute, AgentState, AgentStatus
from app.schemas.diagnosis import MaintenanceDiagnosis


def bind_diagnosis_output(
    model: BaseChatModel,
) -> Runnable:
    return model.with_structured_output(
        MaintenanceDiagnosis,
        method="json_schema",
    )


def create_synthesize_diagnosis_node(
    diagnosis_model: Runnable,
) -> Callable[[AgentState], dict[str, object]]:
    def synthesize_diagnosis(
        state: AgentState,
    ) -> dict[str, object]:
        response = diagnosis_model.invoke(
            [
                SystemMessage(content=DIAGNOSIS_SYNTHESIS_PROMPT),
                build_grounding_context_message(
                    state["evidence_ledger"],
                    state["evidence_coverage"],
                    state["asset_code"],
                ),
                *state["messages"],
            ]
        )

        try:
            diagnosis = (
                response
                if isinstance(response, MaintenanceDiagnosis)
                else MaintenanceDiagnosis.model_validate(response)
            )
        except ValidationError as error:
            return {
                "status": AgentStatus.FAILED,
                "route": AgentRoute.END,
                "visited_nodes": ["synthesize_diagnosis"],
                "error": f"Structured diagnosis validation failed: {error}",
                "diagnosis": None,
            }

        grounded_diagnosis, grounding_result = enforce_grounded_diagnosis(
            diagnosis,
            state["evidence_ledger"],
            state["evidence_coverage"],
            state["asset_code"],
        )

        return {
            "status": AgentStatus.COMPLETED,
            "route": AgentRoute.END,
            "visited_nodes": ["synthesize_diagnosis"],
            "error": None,
            "diagnosis": grounded_diagnosis,
            "grounding_result": grounding_result,
        }

    return synthesize_diagnosis
