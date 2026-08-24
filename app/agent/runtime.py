from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import chromadb
from sqlalchemy.orm import Session

from app.agent.checkpoint import open_sqlite_checkpointer
from app.agent.graph import build_agent_graph
from app.agent.proposal import create_propose_work_order_node
from app.agent.synthesis import bind_diagnosis_output
from app.agent.tool_adapters import (
    InvestigationToolDependencies,
    build_investigation_tools,
)
from app.agent.tool_binding import bind_investigation_tools
from app.core.config import Settings, get_settings
from app.db.session import SessionLocal
from app.llm.provider import create_chat_model
from app.rag.embeddings import (
    SentenceTransformerEmbeddingProvider,
)
from app.services.agent_workflows import AgentGraph

DatabaseSessionFactory = Callable[[], Session]


@dataclass(frozen=True)
class AgentRuntime:
    graph: AgentGraph


@contextmanager
def open_agent_runtime(
    settings: Settings | None = None,
    *,
    session_factory: DatabaseSessionFactory = SessionLocal,
) -> Iterator[AgentRuntime]:
    resolved_settings = settings or get_settings()
    vector_store_path = Path(resolved_settings.vector_store_path)
    vector_store_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    vector_client = chromadb.PersistentClient(
        path=str(vector_store_path),
    )
    embedding_provider = SentenceTransformerEmbeddingProvider(
        resolved_settings.embedding_model_name
    )
    tools = build_investigation_tools(
        InvestigationToolDependencies(
            session_factory=session_factory,
            vector_client=vector_client,
            embedding_provider=embedding_provider,
            engineering_docs_collection=(resolved_settings.engineering_docs_collection),
        )
    )

    raw_model = create_chat_model(
        resolved_settings,
    )
    investigation_model = bind_investigation_tools(
        raw_model,
        tools,
    )
    diagnosis_model = bind_diagnosis_output(
        raw_model,
    )
    proposal_node = create_propose_work_order_node(
        session_factory,
    )

    with open_sqlite_checkpointer(resolved_settings.langgraph_checkpoint_path) as checkpointer:
        graph = build_agent_graph(
            investigation_model,
            tools,
            diagnosis_model=diagnosis_model,
            proposal_node=proposal_node,
            checkpointer=checkpointer,
            observability_session_factory=session_factory,
        )

        yield AgentRuntime(
            graph=graph,
        )
