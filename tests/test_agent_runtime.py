from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.agent.runtime import open_agent_runtime
from app.core.config import Settings


@pytest.fixture
def runtime_dependencies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=f"sqlite:///{(tmp_path / 'runtime.sqlite').as_posix()}",
        langgraph_checkpoint_path=str(tmp_path / "runtime_checkpoints.sqlite"),
        engineering_docs_collection="runtime_engineering_docs",
        embedding_model_name="fake-embedding-model",
    )
    engine = Mock()
    vector_client = Mock()
    embedding_provider = Mock()
    raw_model = Mock()
    investigation_model = Mock()
    diagnosis_model = Mock()
    tools = [Mock(), Mock(), Mock(), Mock()]
    proposal_node = Mock()
    checkpointer = Mock()
    graph = Mock()
    checkpoint_state = {"closed": False}

    factories = {
        "create_engine": Mock(return_value=engine),
        "SQLVectorStore": Mock(return_value=vector_client),
        "SentenceTransformerEmbeddingProvider": Mock(return_value=embedding_provider),
        "build_investigation_tools": Mock(return_value=tools),
        "create_chat_model": Mock(return_value=raw_model),
        "bind_investigation_tools": Mock(return_value=investigation_model),
        "bind_diagnosis_output": Mock(return_value=diagnosis_model),
        "create_propose_work_order_node": Mock(return_value=proposal_node),
        "build_agent_graph": Mock(return_value=graph),
    }

    for name, factory in factories.items():
        monkeypatch.setattr(f"app.agent.runtime.{name}", factory)

    @contextmanager
    def fake_open_checkpointer(checkpoint_path: str) -> Iterator[Mock]:
        assert checkpoint_path == settings.langgraph_checkpoint_path
        try:
            yield checkpointer
        finally:
            checkpoint_state["closed"] = True

    monkeypatch.setattr(
        "app.agent.runtime.open_sqlite_checkpointer",
        fake_open_checkpointer,
    )

    return {
        "settings": settings,
        "engine": engine,
        "vector_client": vector_client,
        "embedding_provider": embedding_provider,
        "raw_model": raw_model,
        "investigation_model": investigation_model,
        "diagnosis_model": diagnosis_model,
        "tools": tools,
        "proposal_node": proposal_node,
        "checkpointer": checkpointer,
        "graph": graph,
        "checkpoint_state": checkpoint_state,
        "factories": factories,
    }


def test_open_agent_runtime_composes_shared_dependencies(runtime_dependencies) -> None:
    dependencies = runtime_dependencies
    settings = dependencies["settings"]
    factories = dependencies["factories"]
    session_factory = Mock()

    with open_agent_runtime(
        settings,
        session_factory=session_factory,
    ) as runtime:
        assert runtime.graph is dependencies["graph"]
        assert dependencies["checkpoint_state"]["closed"] is False
        dependencies["engine"].dispose.assert_not_called()

    assert dependencies["checkpoint_state"]["closed"] is True
    dependencies["engine"].dispose.assert_called_once_with()

    factories["create_engine"].assert_called_once_with(
        settings.database_url,
        pool_pre_ping=True,
    )
    factories["SQLVectorStore"].assert_called_once_with(dependencies["engine"])
    factories["SentenceTransformerEmbeddingProvider"].assert_called_once_with(
        "fake-embedding-model"
    )

    tool_dependencies = factories["build_investigation_tools"].call_args.args[0]
    assert tool_dependencies.session_factory is session_factory
    assert tool_dependencies.vector_client is dependencies["vector_client"]
    assert tool_dependencies.embedding_provider is dependencies["embedding_provider"]
    assert tool_dependencies.engineering_docs_collection == "runtime_engineering_docs"

    factories["create_chat_model"].assert_called_once_with(settings)
    factories["bind_investigation_tools"].assert_called_once_with(
        dependencies["raw_model"],
        dependencies["tools"],
    )
    factories["bind_diagnosis_output"].assert_called_once_with(dependencies["raw_model"])
    factories["create_propose_work_order_node"].assert_called_once_with(session_factory)
    factories["build_agent_graph"].assert_called_once_with(
        dependencies["investigation_model"],
        dependencies["tools"],
        diagnosis_model=dependencies["diagnosis_model"],
        proposal_node=dependencies["proposal_node"],
        checkpointer=dependencies["checkpointer"],
        observability_session_factory=session_factory,
    )


def test_open_agent_runtime_closes_checkpoint_on_build_failure(
    runtime_dependencies,
) -> None:
    dependencies = runtime_dependencies
    dependencies["factories"]["build_agent_graph"].side_effect = RuntimeError(
        "Synthetic graph build failure."
    )

    with pytest.raises(RuntimeError, match="Synthetic graph build failure"):
        with open_agent_runtime(
            dependencies["settings"],
            session_factory=Mock(),
        ):
            pytest.fail("The runtime must not yield after build failure.")

    assert dependencies["checkpoint_state"]["closed"] is True
    dependencies["engine"].dispose.assert_called_once_with()


def test_open_agent_runtime_disposes_engine_on_model_failure(
    runtime_dependencies,
) -> None:
    dependencies = runtime_dependencies
    dependencies["factories"]["create_chat_model"].side_effect = RuntimeError(
        "Synthetic model initialization failure."
    )

    with pytest.raises(RuntimeError, match="Synthetic model initialization failure"):
        with open_agent_runtime(
            dependencies["settings"],
            session_factory=Mock(),
        ):
            pytest.fail("The runtime must not yield after model failure.")

    dependencies["engine"].dispose.assert_called_once_with()
    dependencies["factories"]["build_agent_graph"].assert_not_called()
