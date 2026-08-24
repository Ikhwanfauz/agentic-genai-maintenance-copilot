from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.agent.runtime import open_agent_runtime
from app.core.config import Settings


def create_test_settings(
    tmp_path: Path,
) -> Settings:
    return Settings(
        app_env="test",
        vector_store_path=str(tmp_path / "runtime_chroma"),
        langgraph_checkpoint_path=str(tmp_path / "runtime_checkpoints.sqlite"),
        engineering_docs_collection=("runtime_engineering_docs"),
        embedding_model_name="fake-embedding-model",
    )


def test_open_agent_runtime_composes_shared_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = create_test_settings(tmp_path)
    session_factory = Mock()
    vector_client = Mock()
    embedding_provider = Mock()
    raw_model = Mock()
    investigation_model = Mock()
    diagnosis_model = Mock()
    tools = [Mock(), Mock(), Mock(), Mock()]
    proposal_node = Mock()
    checkpointer = Mock()
    graph = Mock()
    checkpoint_state = {
        "closed": False,
    }

    persistent_client_factory = Mock(
        return_value=vector_client,
    )
    embedding_factory = Mock(
        return_value=embedding_provider,
    )
    tool_factory = Mock(
        return_value=tools,
    )
    model_factory = Mock(
        return_value=raw_model,
    )
    investigation_binding = Mock(
        return_value=investigation_model,
    )
    diagnosis_binding = Mock(
        return_value=diagnosis_model,
    )
    proposal_factory = Mock(
        return_value=proposal_node,
    )
    graph_factory = Mock(
        return_value=graph,
    )

    @contextmanager
    def fake_open_checkpointer(
        checkpoint_path: str,
    ) -> Iterator[Mock]:
        assert checkpoint_path == (settings.langgraph_checkpoint_path)

        try:
            yield checkpointer
        finally:
            checkpoint_state["closed"] = True

    monkeypatch.setattr(
        "app.agent.runtime.chromadb.PersistentClient",
        persistent_client_factory,
    )
    monkeypatch.setattr(
        ("app.agent.runtime.SentenceTransformerEmbeddingProvider"),
        embedding_factory,
    )
    monkeypatch.setattr(
        "app.agent.runtime.build_investigation_tools",
        tool_factory,
    )
    monkeypatch.setattr(
        "app.agent.runtime.create_chat_model",
        model_factory,
    )
    monkeypatch.setattr(
        "app.agent.runtime.bind_investigation_tools",
        investigation_binding,
    )
    monkeypatch.setattr(
        "app.agent.runtime.bind_diagnosis_output",
        diagnosis_binding,
    )
    monkeypatch.setattr(
        "app.agent.runtime.create_propose_work_order_node",
        proposal_factory,
    )
    monkeypatch.setattr(
        "app.agent.runtime.open_sqlite_checkpointer",
        fake_open_checkpointer,
    )
    monkeypatch.setattr(
        "app.agent.runtime.build_agent_graph",
        graph_factory,
    )

    with open_agent_runtime(
        settings,
        session_factory=session_factory,
    ) as runtime:
        assert runtime.graph is graph
        assert checkpoint_state["closed"] is False

    assert checkpoint_state["closed"] is True
    assert (tmp_path / "runtime_chroma").is_dir()

    persistent_client_factory.assert_called_once_with(
        path=str(tmp_path / "runtime_chroma"),
    )
    embedding_factory.assert_called_once_with(
        "fake-embedding-model",
    )

    dependencies = tool_factory.call_args.args[0]
    assert dependencies.session_factory is session_factory
    assert dependencies.vector_client is vector_client
    assert dependencies.embedding_provider is embedding_provider
    assert dependencies.engineering_docs_collection == "runtime_engineering_docs"

    model_factory.assert_called_once_with(settings)
    investigation_binding.assert_called_once_with(
        raw_model,
        tools,
    )
    diagnosis_binding.assert_called_once_with(
        raw_model,
    )
    proposal_factory.assert_called_once_with(
        session_factory,
    )
    graph_factory.assert_called_once_with(
        investigation_model,
        tools,
        diagnosis_model=diagnosis_model,
        proposal_node=proposal_node,
        checkpointer=checkpointer,
    )


def test_open_agent_runtime_closes_checkpoint_on_build_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = create_test_settings(tmp_path)
    checkpoint_state = {
        "closed": False,
    }

    monkeypatch.setattr(
        "app.agent.runtime.chromadb.PersistentClient",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(
        ("app.agent.runtime.SentenceTransformerEmbeddingProvider"),
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(
        "app.agent.runtime.build_investigation_tools",
        Mock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.agent.runtime.create_chat_model",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(
        "app.agent.runtime.bind_investigation_tools",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(
        "app.agent.runtime.bind_diagnosis_output",
        Mock(return_value=Mock()),
    )
    monkeypatch.setattr(
        "app.agent.runtime.create_propose_work_order_node",
        Mock(return_value=Mock()),
    )

    @contextmanager
    def fake_open_checkpointer(
        _checkpoint_path: str,
    ) -> Iterator[Mock]:
        try:
            yield Mock()
        finally:
            checkpoint_state["closed"] = True

    monkeypatch.setattr(
        "app.agent.runtime.open_sqlite_checkpointer",
        fake_open_checkpointer,
    )
    monkeypatch.setattr(
        "app.agent.runtime.build_agent_graph",
        Mock(side_effect=RuntimeError("Synthetic graph build failure.")),
    )

    with pytest.raises(
        RuntimeError,
        match="Synthetic graph build failure",
    ):
        with open_agent_runtime(
            settings,
            session_factory=Mock(),
        ):
            pytest.fail("The runtime must not yield after build failure.")

    assert checkpoint_state["closed"] is True
