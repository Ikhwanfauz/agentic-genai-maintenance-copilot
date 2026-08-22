import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import Mock

import chromadb
import pytest
from chromadb.api import ClientAPI
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.agent.graph import build_agent_graph
from app.agent.state import AgentStatus, create_initial_state
from app.agent.tool_adapters import (
    InvestigationToolDependencies,
    build_investigation_tools,
)
from app.db.base import Base
from app.db.seed_reference import seed_reference_data
from app.db.seed_sensor import seed_sensor_data
from app.models.approval import Approval
from app.models.asset import Asset
from app.models.maintenance import MaintenanceRecord
from app.models.sensor import SensorReading
from app.models.work_order import WorkOrder
from app.rag.indexer import index_engineering_documents
from app.schemas.diagnosis import (
    DiagnosisConfidence,
    EvidenceReference,
    EvidenceSourceType,
    InvestigationOutcome,
    MaintenanceDiagnosis,
)

REFERENCE_TIME = datetime(2026, 8, 19, tzinfo=UTC)
COLLECTION_NAME = "v44_engineering_docs"


class ScenarioEmbeddingProvider:
    @staticmethod
    def embed_text(text: str) -> list[float]:
        normalized_text = text.lower()
        groups = (
            ("vibration", "bearing", "alignment", "coupling", "motor"),
            ("flow", "pressure", "cavitation", "suction", "impeller"),
            ("approval", "lockout", "isolation", "work order", "control"),
        )
        vector = [
            float(sum(normalized_text.count(term) for term in group) + 0.1) for group in groups
        ]
        magnitude = math.sqrt(sum(value**2 for value in vector))

        return [value / magnitude for value in vector]

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_text(text)


@dataclass(frozen=True)
class ScenarioEnvironment:
    engine: Engine
    vector_client: ClientAPI
    tools: list[BaseTool]
    baseline_sql_counts: dict[str, int]
    baseline_vector_count: int


def count_sql_rows(engine: Engine) -> dict[str, int]:
    models = {
        "assets": Asset,
        "maintenance_records": MaintenanceRecord,
        "sensor_readings": SensorReading,
        "work_orders": WorkOrder,
        "approvals": Approval,
    }

    with Session(engine) as database_session:
        return {
            name: int(database_session.scalar(select(func.count()).select_from(model)) or 0)
            for name, model in models.items()
        }


@pytest.fixture(scope="module")
def scenario_environment(
    tmp_path_factory: pytest.TempPathFactory,
) -> ScenarioEnvironment:
    database_path = tmp_path_factory.mktemp("v44") / "scenario.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(engine)

    with Session(engine, expire_on_commit=False) as database_session:
        assets = seed_reference_data(database_session, REFERENCE_TIME)
        seed_sensor_data(database_session, assets, REFERENCE_TIME)
        database_session.commit()

    vector_client = chromadb.EphemeralClient()
    embedding_provider = ScenarioEmbeddingProvider()
    index_engineering_documents(
        client=vector_client,
        embedding_provider=embedding_provider,
        documents_directory=Path("data/engineering_docs"),
        collection_name=COLLECTION_NAME,
    )
    tools = build_investigation_tools(
        InvestigationToolDependencies(
            session_factory=lambda: Session(engine, expire_on_commit=False),
            vector_client=vector_client,
            embedding_provider=embedding_provider,
            engineering_docs_collection=COLLECTION_NAME,
        )
    )

    return ScenarioEnvironment(
        engine=engine,
        vector_client=vector_client,
        tools=tools,
        baseline_sql_counts=count_sql_rows(engine),
        baseline_vector_count=vector_client.get_collection(name=COLLECTION_NAME).count(),
    )


def assert_environment_unchanged(environment: ScenarioEnvironment) -> None:
    assert count_sql_rows(environment.engine) == environment.baseline_sql_counts
    assert (
        environment.vector_client.get_collection(name=COLLECTION_NAME).count()
        == environment.baseline_vector_count
    )


def tool_call(
    name: str,
    arguments: dict[str, object],
    index: int,
) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": name,
                "args": arguments,
                "id": f"scenario-tool-call-{index}",
                "type": "tool_call",
            }
        ],
    )


def grounding_metadata(messages: list[object]) -> dict[str, object]:
    grounding_message = next(
        message
        for message in messages
        if isinstance(message, SystemMessage)
        and message.content.startswith("Application-owned grounding metadata")
    )

    return json.loads(grounding_message.content.split("\n", maxsplit=1)[1])


def create_claimed_diagnosis(messages: list[object]) -> MaintenanceDiagnosis:
    metadata = grounding_metadata(messages)
    allowlist = metadata["citation_allowlist"]

    return MaintenanceDiagnosis(
        asset_code=metadata["target_asset_code"],
        outcome=InvestigationOutcome.DIAGNOSIS,
        summary=(
            "P-101 shows a developing vibration condition requiring approved physical inspection."
        ),
        confidence=DiagnosisConfidence.MEDIUM,
        confidence_rationale=(
            "The conclusion uses asset, maintenance, sensor, and engineering guidance."
        ),
        likely_causes=["Developing coupling alignment or bearing condition issue"],
        evidence=[
            EvidenceReference(
                source_type=EvidenceSourceType(item["source_type"]),
                source_id=item["source_id"],
                summary=f"Grounded {item['source_type']} evidence.",
                citation=item["citation"],
            )
            for item in allowlist
        ],
        recommended_actions=[],
        safety_notes=[
            "Use approved isolation and human-reviewed work processes before inspection."
        ],
    )


def create_insufficient_diagnosis(_messages: list[object]) -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code="P-101",
        outcome=InvestigationOutcome.INSUFFICIENT_EVIDENCE,
        summary="The tool failure prevents a grounded maintenance diagnosis.",
        confidence=DiagnosisConfidence.LOW,
        confidence_rationale="Required asset evidence was not available.",
        safety_notes=["Do not act until the failed evidence source is recovered."],
        abstention_reason="A required investigation tool failed.",
    )


def create_out_of_scope_diagnosis(_messages: list[object]) -> MaintenanceDiagnosis:
    return MaintenanceDiagnosis(
        asset_code=None,
        outcome=InvestigationOutcome.OUT_OF_SCOPE,
        summary="The request is outside rotating-equipment maintenance.",
        confidence=DiagnosisConfidence.LOW,
        confidence_rationale="The request does not concern a supported asset.",
        safety_notes=["No maintenance action was proposed."],
        abstention_reason="The request is outside the copilot scope.",
    )


def test_p101_complete_investigation_returns_grounded_diagnosis(
    scenario_environment: ScenarioEnvironment,
) -> None:
    investigation_model = Mock()
    investigation_model.invoke.side_effect = [
        tool_call("get_asset_details", {"asset_code": "P-101"}, 1),
        tool_call(
            "query_maintenance_history",
            {"asset_code": "P-101", "limit": 3},
            2,
        ),
        tool_call(
            "analyze_sensor_data",
            {
                "asset_code": "P-101",
                "sensor_types": ["vibration", "flow_rate"],
            },
            3,
        ),
        tool_call(
            "search_engineering_docs",
            {
                "query": "increasing vibration coupling alignment isolation",
                "asset_code": "P-101",
                "top_k": 3,
                "minimum_relevance": 0.0,
            },
            4,
        ),
        AIMessage(content="All required evidence categories were gathered."),
    ]
    diagnosis_model = Mock()
    diagnosis_model.invoke.side_effect = create_claimed_diagnosis
    graph = build_agent_graph(
        investigation_model,
        scenario_environment.tools,
        diagnosis_model=diagnosis_model,
    )

    result = graph.invoke(
        create_initial_state(
            "Investigate increasing vibration on P-101",
            "P-101",
            max_iterations=6,
            run_id="v44-p101-grounded",
        )
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert result["evidence_coverage"].decision == "ready", {
        "missing": [source.value for source in result["evidence_coverage"].missing_sources],
        "evidence_types": [evidence.source_type.value for evidence in result["evidence_ledger"]],
        "tool_errors": [
            (message.name, message.content)
            for message in result["messages"]
            if isinstance(message, ToolMessage) and message.status == "error"
        ],
    }
    assert result["grounding_result"].decision == "grounded"
    assert result["grounding_result"].downgraded is False
    assert result["diagnosis"].outcome == InvestigationOutcome.DIAGNOSIS
    assert result["diagnosis"].asset_code == "P-101"
    assert {evidence.source_type for evidence in result["evidence_ledger"]} == set(
        result["evidence_coverage"].required_sources
    )
    assert len(result["diagnosis"].evidence) == len(result["evidence_ledger"])
    assert investigation_model.invoke.call_count == 5
    assert diagnosis_model.invoke.call_count == 1
    assert_environment_unchanged(scenario_environment)


def test_incomplete_investigation_downgrades_claimed_diagnosis(
    scenario_environment: ScenarioEnvironment,
) -> None:
    investigation_model = Mock()
    investigation_model.invoke.side_effect = [
        tool_call("get_asset_details", {"asset_code": "P-101"}, 1),
        AIMessage(content="Stopping before other evidence sources are gathered."),
    ]
    diagnosis_model = Mock()
    diagnosis_model.invoke.side_effect = create_claimed_diagnosis
    graph = build_agent_graph(
        investigation_model,
        scenario_environment.tools,
        diagnosis_model=diagnosis_model,
    )

    result = graph.invoke(
        create_initial_state(
            "Investigate P-101 with incomplete evidence",
            "P-101",
            max_iterations=3,
            run_id="v44-p101-incomplete",
        )
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert result["evidence_coverage"].decision == "incomplete"
    assert result["diagnosis"].outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert result["grounding_result"].decision == "abstained"
    assert result["grounding_result"].downgraded is True
    assert any(
        "coverage is incomplete" in violation for violation in result["grounding_result"].violations
    )
    assert_environment_unchanged(scenario_environment)


def test_tool_failure_abstains_without_collecting_failed_output(
    scenario_environment: ScenarioEnvironment,
) -> None:
    investigation_model = Mock()
    investigation_model.invoke.side_effect = [
        tool_call("get_asset_details", {"asset_code": "P-999"}, 1),
        AIMessage(content="The required asset tool failed."),
    ]
    diagnosis_model = Mock()
    diagnosis_model.invoke.side_effect = create_insufficient_diagnosis
    graph = build_agent_graph(
        investigation_model,
        scenario_environment.tools,
        diagnosis_model=diagnosis_model,
    )

    result = graph.invoke(
        create_initial_state(
            "Investigate P-101 after a controlled tool failure",
            "P-101",
            max_iterations=3,
            run_id="v44-tool-failure",
        )
    )

    tool_messages = [message for message in result["messages"] if isinstance(message, ToolMessage)]
    assert result["status"] == AgentStatus.COMPLETED
    assert len(tool_messages) == 1
    assert tool_messages[0].status == "error"
    assert result["evidence_ledger"] == []
    assert result["evidence_coverage"].decision == "incomplete"
    assert result["diagnosis"].outcome == InvestigationOutcome.INSUFFICIENT_EVIDENCE
    assert result["grounding_result"].decision == "abstained"
    assert result["grounding_result"].downgraded is False
    assert_environment_unchanged(scenario_environment)


def test_out_of_scope_request_ends_without_tool_execution(
    scenario_environment: ScenarioEnvironment,
) -> None:
    investigation_model = Mock()
    investigation_model.invoke.return_value = AIMessage(
        content="This request is outside rotating-equipment maintenance."
    )
    diagnosis_model = Mock()
    diagnosis_model.invoke.side_effect = create_out_of_scope_diagnosis
    graph = build_agent_graph(
        investigation_model,
        scenario_environment.tools,
        diagnosis_model=diagnosis_model,
    )

    result = graph.invoke(
        create_initial_state(
            "Write a marketing slogan",
            max_iterations=2,
            run_id="v44-out-of-scope",
        )
    )

    assert result["status"] == AgentStatus.COMPLETED
    assert result["evidence_coverage"].decision == "asset_scope_required"
    assert result["evidence_ledger"] == []
    assert not any(isinstance(message, ToolMessage) for message in result["messages"])
    assert result["diagnosis"].outcome == InvestigationOutcome.OUT_OF_SCOPE
    assert result["grounding_result"].decision == "out_of_scope"
    assert result["grounding_result"].downgraded is False
    assert investigation_model.invoke.call_count == 1
    assert_environment_unchanged(scenario_environment)
