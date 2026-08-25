from collections.abc import Callable, Sequence
from typing import Literal

from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agent.approval import (
    await_work_order_approval,
    prepare_approval_pause,
)
from app.agent.model_observability import (
    create_failed_model_usage_observer,
    create_model_usage_observer,
)
from app.agent.nodes import create_call_model_node
from app.agent.observability import (
    ObservedNodeFailure,
    ObservedNodeSuccess,
    create_observed_node,
)
from app.agent.policy import evaluate_evidence_coverage
from app.agent.state import AgentRoute, AgentState, AgentStatus
from app.agent.synthesis import create_synthesize_diagnosis_node
from app.agent.tool_node import create_execute_tools_node
from app.agent.tool_observability import (
    create_tool_call_observer,
)
from app.models.enums import AgentStepType
from app.schemas.diagnosis import InvestigationOutcome
from app.schemas.investigation import GroundingDecision

AgentNode = Callable[[AgentState], dict[str, object]]
WorkOrderProposalNode = AgentNode
ObservabilitySessionFactory = Callable[[], Session]


def _observe_node(
    node: AgentNode,
    session_factory: ObservabilitySessionFactory | None,
    *,
    step_type: AgentStepType,
    summary: str,
    on_success: ObservedNodeSuccess | None = None,
    on_failure: ObservedNodeFailure | None = None,
) -> AgentNode:
    if session_factory is None:
        return node

    return create_observed_node(
        node,
        session_factory,
        step_type=step_type,
        summary=summary,
        on_success=on_success,
        on_failure=on_failure,
    )


def initialize_request(_state: AgentState) -> dict[str, object]:
    return {
        "status": AgentStatus.RUNNING,
        "visited_nodes": ["initialize"],
    }


def route_request(
    state: AgentState,
) -> Literal["mark_ready", "reject_request"]:
    if not state["user_query"]:
        return "reject_request"

    return "mark_ready"


def route_after_model_without_synthesis(
    state: AgentState,
) -> Literal["execute_tools", "__end__"]:
    if state["route"] == AgentRoute.TOOLS:
        return "execute_tools"

    return END


def route_after_model_with_synthesis(
    state: AgentState,
) -> Literal[
    "execute_tools",
    "synthesize_diagnosis",
    "__end__",
]:
    if state["route"] == AgentRoute.TOOLS:
        return "execute_tools"

    if state["route"] == AgentRoute.SYNTHESIZE:
        return "synthesize_diagnosis"

    return END


def route_grounded_diagnosis_to_proposal(
    state: AgentState,
) -> Literal["propose_work_order", "__end__"]:
    diagnosis = state["diagnosis"]
    grounding_result = state["grounding_result"]

    if (
        diagnosis is not None
        and diagnosis.outcome == InvestigationOutcome.DIAGNOSIS
        and grounding_result is not None
        and grounding_result.decision == GroundingDecision.GROUNDED
        and not grounding_result.downgraded
    ):
        return "propose_work_order"

    return END


def route_proposal_to_approval(
    state: AgentState,
) -> Literal["prepare_approval_pause", "__end__"]:
    if state["work_order_proposal"] is not None:
        return "prepare_approval_pause"

    return END


def mark_ready(state: AgentState) -> dict[str, object]:
    return {
        "status": AgentStatus.READY,
        "route": AgentRoute.INVESTIGATE,
        "visited_nodes": ["mark_ready"],
        "error": None,
        "evidence_coverage": evaluate_evidence_coverage(
            state["evidence_ledger"],
            state["asset_code"],
        ),
    }


def reject_request(_state: AgentState) -> dict[str, object]:
    return {
        "status": AgentStatus.REJECTED,
        "route": AgentRoute.END,
        "visited_nodes": ["reject_request"],
        "error": "A non-empty maintenance investigation request is required.",
    }


def build_state_flow():
    builder = StateGraph(AgentState)

    builder.add_node("initialize", initialize_request)
    builder.add_node("mark_ready", mark_ready)
    builder.add_node("reject_request", reject_request)

    builder.add_edge(START, "initialize")
    builder.add_conditional_edges("initialize", route_request)
    builder.add_edge("mark_ready", END)
    builder.add_edge("reject_request", END)

    return builder.compile()


def build_agent_graph(
    model: Runnable,
    tools: Sequence[BaseTool] = (),
    *,
    diagnosis_model: Runnable | None = None,
    proposal_node: WorkOrderProposalNode | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
    observability_session_factory: ObservabilitySessionFactory | None = None,
):

    if proposal_node is not None and diagnosis_model is None:
        raise ValueError("A work-order proposal node requires a diagnosis model.")

    if proposal_node is not None and checkpointer is None:
        raise ValueError("A work-order proposal node requires a LangGraph checkpointer.")
    builder = StateGraph(AgentState)

    initialize_node = _observe_node(
        initialize_request,
        observability_session_factory,
        step_type=AgentStepType.ROUTING,
        summary="Initialized the maintenance investigation.",
    )
    mark_ready_node = _observe_node(
        mark_ready,
        observability_session_factory,
        step_type=AgentStepType.GUARDRAIL,
        summary="Validated the investigation request and evidence coverage.",
    )
    reject_request_node = _observe_node(
        reject_request,
        observability_session_factory,
        step_type=AgentStepType.GUARDRAIL,
        summary="Rejected an invalid maintenance investigation request.",
    )
    model_usage_observer = (
        create_model_usage_observer(observability_session_factory)
        if observability_session_factory is not None
        else None
    )
    failed_model_usage_observer = (
        create_failed_model_usage_observer(observability_session_factory)
        if observability_session_factory is not None
        else None
    )
    call_model_node = _observe_node(
        create_call_model_node(
            model,
            require_structured_diagnosis=diagnosis_model is not None,
        ),
        observability_session_factory,
        step_type=AgentStepType.TOOL_SELECTION,
        summary="Selected the next maintenance investigation action.",
        on_success=model_usage_observer,
        on_failure=failed_model_usage_observer,
    )
    tool_call_observer = (
        create_tool_call_observer(observability_session_factory)
        if observability_session_factory is not None
        else None
    )
    execute_tools_node = _observe_node(
        create_execute_tools_node(tools),
        observability_session_factory,
        step_type=AgentStepType.TOOL_EXECUTION,
        summary="Executed a deterministic investigation tool.",
        on_success=tool_call_observer,
    )

    builder.add_node(
        "initialize",
        initialize_node,
    )
    builder.add_node(
        "mark_ready",
        mark_ready_node,
    )
    builder.add_node(
        "reject_request",
        reject_request_node,
    )
    builder.add_node(
        "call_model",
        call_model_node,
    )
    builder.add_node(
        "execute_tools",
        execute_tools_node,
    )

    builder.add_edge(START, "initialize")
    builder.add_conditional_edges("initialize", route_request)
    builder.add_edge("mark_ready", "call_model")
    builder.add_edge("execute_tools", "call_model")
    builder.add_edge("reject_request", END)

    if diagnosis_model is None:
        builder.add_conditional_edges(
            "call_model",
            route_after_model_without_synthesis,
        )
    else:
        diagnosis_usage_observer = (
            create_model_usage_observer(
                observability_session_factory,
                count_without_message=True,
            )
            if observability_session_factory is not None
            else None
        )
        synthesis_node = _observe_node(
            create_synthesize_diagnosis_node(diagnosis_model),
            observability_session_factory,
            step_type=AgentStepType.EVIDENCE_SYNTHESIS,
            summary="Synthesized and validated a grounded diagnosis.",
            on_success=diagnosis_usage_observer,
            on_failure=failed_model_usage_observer,
        )
        builder.add_node(
            "synthesize_diagnosis",
            synthesis_node,
        )
        builder.add_conditional_edges(
            "call_model",
            route_after_model_with_synthesis,
        )
        if proposal_node is None:
            builder.add_edge(
                "synthesize_diagnosis",
                END,
            )
        else:
            observed_proposal_node = _observe_node(
                proposal_node,
                observability_session_factory,
                step_type=AgentStepType.FINAL_RESPONSE,
                summary="Created a grounded work-order proposal.",
            )
            observed_approval_pause_node = _observe_node(
                prepare_approval_pause,
                observability_session_factory,
                step_type=AgentStepType.APPROVAL_PAUSE,
                summary="Prepared the work order for human approval.",
            )

            builder.add_node(
                "propose_work_order",
                observed_proposal_node,
            )
            builder.add_node(
                "prepare_approval_pause",
                observed_approval_pause_node,
            )
            builder.add_node(
                "await_work_order_approval",
                await_work_order_approval,
            )

            builder.add_conditional_edges(
                "synthesize_diagnosis",
                route_grounded_diagnosis_to_proposal,
            )
            builder.add_conditional_edges(
                "propose_work_order",
                route_proposal_to_approval,
            )
            builder.add_edge(
                "prepare_approval_pause",
                "await_work_order_approval",
            )
            builder.add_edge(
                "await_work_order_approval",
                END,
            )

    return builder.compile(
        checkpointer=checkpointer,
    )
