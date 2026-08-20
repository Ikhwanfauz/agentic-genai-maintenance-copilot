from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from app.agent.tool_adapters import (
    InvestigationToolDependencies,
    build_investigation_tools,
)
from app.agent.tool_binding import bind_investigation_tools
from app.schemas.asset import AssetDetailsInput
from app.schemas.maintenance import MaintenanceHistoryInput
from app.schemas.rag import EngineeringDocumentSearchInput
from app.schemas.sensor import SensorAnalysisInput


def create_dependencies(
    session_factory: Mock | None = None,
) -> InvestigationToolDependencies:
    return InvestigationToolDependencies(
        session_factory=session_factory or Mock(),
        vector_client=Mock(),
        embedding_provider=Mock(),
        engineering_docs_collection="test_engineering_docs",
    )


def test_build_investigation_tools_exposes_locked_read_only_tools() -> None:
    tools = build_investigation_tools(create_dependencies())

    assert [tool.name for tool in tools] == [
        "get_asset_details",
        "query_maintenance_history",
        "analyze_sensor_data",
        "search_engineering_docs",
    ]
    assert [tool.args_schema for tool in tools] == [
        AssetDetailsInput,
        MaintenanceHistoryInput,
        SensorAnalysisInput,
        EngineeringDocumentSearchInput,
    ]


def test_asset_adapter_validates_and_calls_deterministic_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_session = Mock()
    session_factory = Mock(return_value=database_session)
    deterministic_result = Mock()
    deterministic_result.model_dump.return_value = {
        "asset_code": "P-101",
        "name": "Main Cooling Water Pump",
    }
    deterministic_tool = Mock(return_value=deterministic_result)
    monkeypatch.setattr(
        "app.agent.tool_adapters.get_asset_details",
        deterministic_tool,
    )

    tools = build_investigation_tools(create_dependencies(session_factory))
    asset_tool = tools[0]

    result = asset_tool.invoke({"asset_code": "P-101"})

    assert result["asset_code"] == "P-101"
    called_input = deterministic_tool.call_args.args[1]
    assert isinstance(called_input, AssetDetailsInput)
    assert called_input.asset_code == "P-101"
    database_session.close.assert_called_once_with()


def test_asset_adapter_rejects_invalid_arguments_before_database_call() -> None:
    session_factory = Mock()
    tools = build_investigation_tools(create_dependencies(session_factory))

    with pytest.raises(ValidationError):
        tools[0].invoke({"asset_code": "invalid"})

    session_factory.assert_not_called()


def test_rag_adapter_calls_existing_semantic_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dependencies = create_dependencies()
    deterministic_result = Mock()
    deterministic_result.model_dump.return_value = {
        "query": "pump vibration",
        "asset_code": "P-101",
        "returned_result_count": 1,
        "results": [],
    }
    deterministic_tool = Mock(return_value=deterministic_result)
    monkeypatch.setattr(
        "app.agent.tool_adapters.search_engineering_docs",
        deterministic_tool,
    )

    tools = build_investigation_tools(dependencies)
    rag_tool = tools[3]

    result = rag_tool.invoke(
        {
            "query": "pump vibration",
            "asset_code": "P-101",
            "top_k": 3,
        }
    )

    assert result["query"] == "pump vibration"
    called_arguments = deterministic_tool.call_args.args
    assert called_arguments[0] is dependencies.vector_client
    assert called_arguments[1] is dependencies.embedding_provider
    assert called_arguments[2] == "test_engineering_docs"
    assert isinstance(
        called_arguments[3],
        EngineeringDocumentSearchInput,
    )


def test_bind_investigation_tools_disables_parallel_calls() -> None:
    model = Mock()
    bound_model = Mock()
    model.bind_tools.return_value = bound_model
    tools = build_investigation_tools(create_dependencies())

    result = bind_investigation_tools(model, tools)

    assert result is bound_model
    model.bind_tools.assert_called_once_with(
        tools,
        parallel_tool_calls=False,
    )
