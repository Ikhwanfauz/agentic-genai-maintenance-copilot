from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.agent.checkpoint import open_sqlite_checkpointer
from app.agent.graph import build_agent_graph
from app.agent.proposal import create_propose_work_order_node
from app.evaluation.contracts import (
    EvaluationDataset,
    EvaluationScenario,
)
from app.evaluation.environment import (
    open_evaluation_scenario_environment,
)
from app.evaluation.execution import (
    EvaluationDatasetResult,
    EvaluationResultStatus,
    EvaluationScenarioObservation,
    EvaluationScenarioResult,
)
from app.evaluation.fixture_registry import get_fixture_plan
from app.evaluation.scoring import score_scenario_observation
from app.evaluation.scripted_models import (
    ScriptedDiagnosisModel,
    ScriptedInvestigationModel,
)
from app.models.agent_log import ToolCall
from app.schemas.agent_api import AgentInvestigationStartRequest
from app.schemas.observability import ToolCallRecordInput
from app.services.agent_workflows import start_agent_investigation

EVALUATION_TIME = datetime(
    2026,
    8,
    27,
    12,
    0,
    tzinfo=UTC,
)


def _stable_identifier(
    prefix: str,
    scenario_id: str,
) -> str:
    digest = sha256(scenario_id.encode("utf-8")).hexdigest()[:24]

    return f"{prefix}-{digest}"


def _load_tool_call_records(
    session_factory: sessionmaker[Session],
    run_id: str,
) -> list[ToolCallRecordInput]:
    with session_factory() as database_session:
        records = list(
            database_session.scalars(
                select(ToolCall).where(ToolCall.run_id == run_id).order_by(ToolCall.id)
            )
        )

    observed_calls: list[ToolCallRecordInput] = []

    for record in records:
        if record.completed_at is None or record.latency_ms is None:
            raise ValueError("Evaluation tool-call records must be completed.")

        observed_calls.append(
            ToolCallRecordInput(
                run_id=record.run_id,
                step_id=record.step_id,
                approval_id=record.approval_id,
                tool_name=record.tool_name,
                arguments_json=dict(record.arguments_json),
                result_json=(dict(record.result_json) if record.result_json is not None else None),
                status=record.status,
                is_state_changing=record.is_state_changing,
                started_at=record.started_at,
                completed_at=record.completed_at,
                latency_ms=record.latency_ms,
                error_type=record.error_type,
                error_message=record.error_message,
            )
        )

    return observed_calls


def _create_execution_error(
    scenario: EvaluationScenario,
    error: Exception,
) -> EvaluationScenarioResult:
    root_error = error

    while isinstance(root_error.__cause__, Exception):
        root_error = root_error.__cause__

    error_message = str(root_error).strip() or type(root_error).__name__

    return EvaluationScenarioResult(
        scenario_id=scenario.scenario_id,
        scenario_version=scenario.scenario_version,
        fixture_id=scenario.fixture_id,
        status=EvaluationResultStatus.ERROR,
        metric_results=[],
        error_type=type(root_error).__name__[:150],
        error_message=error_message[:4000],
    )


def run_evaluation_scenario(
    scenario: EvaluationScenario,
    working_directory: Path,
) -> EvaluationScenarioResult:
    """Execute and score one scenario using local deterministic dependencies."""

    try:
        fixture = get_fixture_plan(
            scenario.fixture_id,
        )
        run_id = _stable_identifier(
            "eval",
            scenario.scenario_id,
        )
        thread_id = run_id
        work_order_number = (
            f"WO-EVAL-{sha256(scenario.scenario_id.encode('utf-8')).hexdigest()[:16].upper()}"
        )

        with open_evaluation_scenario_environment(
            working_directory,
            fixture,
        ) as environment:
            proposal_node = create_propose_work_order_node(
                environment.session_factory,
                proposed_by="evaluation-runner",
                work_order_number_factory=(lambda: work_order_number),
            )

            with open_sqlite_checkpointer(environment.checkpoint_path) as checkpointer:
                graph = build_agent_graph(
                    ScriptedInvestigationModel(fixture),
                    environment.tools,
                    diagnosis_model=(ScriptedDiagnosisModel(fixture)),
                    proposal_node=proposal_node,
                    checkpointer=checkpointer,
                    observability_session_factory=(environment.session_factory),
                )

                request = AgentInvestigationStartRequest(
                    user_query=scenario.request.user_query,
                    asset_code=scenario.request.asset_code,
                    thread_id=thread_id,
                    max_iterations=scenario.request.max_iterations,
                )

                with environment.session_factory() as database_session:
                    run = start_agent_investigation(
                        database_session,
                        graph,
                        request,
                        workflow_clock=lambda: EVALUATION_TIME,
                        run_id_factory=lambda: run_id,
                        model_provider="evaluation",
                        model_name="scripted-fixture",
                    )

                snapshot = graph.get_state(
                    {
                        "configurable": {
                            "thread_id": thread_id,
                        }
                    }
                )
                state = dict(snapshot.values)

            observation = EvaluationScenarioObservation(
                scenario_id=scenario.scenario_id,
                run=run,
                grounding_result=state.get("grounding_result"),
                evidence_coverage=state.get("evidence_coverage"),
                evidence_ledger=list(state.get("evidence_ledger", [])),
                tool_calls=_load_tool_call_records(
                    environment.session_factory,
                    run_id,
                ),
                iteration_count=int(state.get("iteration_count", 0)),
                max_iterations=int(
                    state.get(
                        "max_iterations",
                        scenario.request.max_iterations,
                    )
                ),
                visited_nodes=list(state.get("visited_nodes", [])),
            )

            return score_scenario_observation(
                scenario,
                observation,
            )
    except Exception as error:
        return _create_execution_error(
            scenario,
            error,
        )


def run_evaluation_dataset(
    dataset: EvaluationDataset,
    working_directory: Path,
) -> EvaluationDatasetResult:
    """Execute every scenario and return one aggregate result."""

    scenario_results = [
        run_evaluation_scenario(
            scenario,
            working_directory / scenario.fixture_id,
        )
        for scenario in dataset.scenarios
    ]
    scenario_statuses = {result.status for result in scenario_results}

    if EvaluationResultStatus.ERROR in scenario_statuses:
        status = EvaluationResultStatus.ERROR
    elif EvaluationResultStatus.FAILED in scenario_statuses:
        status = EvaluationResultStatus.FAILED
    else:
        status = EvaluationResultStatus.PASSED

    return EvaluationDatasetResult(
        dataset_id=dataset.dataset_id,
        dataset_version=dataset.dataset_version,
        status=status,
        scenario_results=scenario_results,
    )
