import math
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from langchain_core.tools import BaseTool
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.agent.tool_adapters import (
    InvestigationToolDependencies,
    build_investigation_tools,
)
from app.db.base import Base
from app.db.seed_reference import seed_reference_data
from app.db.seed_sensor import seed_sensor_data
from app.db.session import create_database_engine
from app.evaluation.fixtures import ScenarioFixturePlan
from app.evaluation.mutations import apply_fixture_mutations
from app.rag.indexer import index_engineering_documents

EVALUATION_REFERENCE_TIME = datetime(
    2026,
    8,
    19,
    tzinfo=UTC,
)
EVALUATION_COLLECTION_NAME = "v73_engineering_docs"


class EvaluationEmbeddingProvider:
    """Section-aware deterministic embeddings for the evaluation corpus."""

    _SECTION_NAMES = (
        "elevated vibration",
        "reduced flow and discharge pressure",
        "cavitation indicators",
        "correlated pump and motor vibration",
        "motor current and temperature",
        "alignment inspection",
        "evidence requirements",
        "work-order approval",
        "machinery control boundary",
    )

    @staticmethod
    def _normalize(
        values: list[float],
    ) -> list[float]:
        magnitude = math.sqrt(sum(value**2 for value in values))

        return [value / magnitude for value in values]

    @classmethod
    def _embed_document(
        cls,
        text: str,
    ) -> list[float]:
        normalized_text = text.lower()
        values = [0.01 for _section_name in cls._SECTION_NAMES]

        for index, section_name in enumerate(cls._SECTION_NAMES):
            if f"section: {section_name}" in normalized_text:
                values[index] = 1.0

                return cls._normalize(values)

        raise ValueError("Evaluation document does not contain a recognized section.")

    @classmethod
    def _embed_query(
        cls,
        text: str,
    ) -> list[float]:
        normalized_text = text.lower()
        values = [0.01 for _section_name in cls._SECTION_NAMES]
        query_features = (
            (
                "vibration",
                "bearing",
                "coupling",
                "trend interpretation",
                "condition verification",
            ),
            (
                "flow",
                "discharge pressure",
                "hydraulic",
                "suction pressure",
            ),
            ("cavitation",),
            (
                "correlated",
                "pump and motor",
                "motor vibration",
            ),
            (
                "motor current",
                "electrical",
            ),
            (
                "alignment",
                "inspection",
                "isolation",
                "lockout",
            ),
            (
                "evidence",
                "data quality",
                "data-quality",
                "limitation",
                "maintenance history",
                "instrument validity",
                "requirements",
                "unsupported",
            ),
            (
                "approval",
                "work order",
                "human",
                "supervisor",
                "authorize",
            ),
            (
                "machinery control",
                "direct control",
                "plc",
                "interlock",
                "stop",
                "start",
                "executed",
            ),
        )

        for index, features in enumerate(query_features):
            if any(feature in normalized_text for feature in features):
                values[index] = 1.0

        return cls._normalize(values)

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        return [self._embed_document(text) for text in texts]

    def embed_query(
        self,
        text: str,
    ) -> list[float]:
        return self._embed_query(text)


@dataclass(frozen=True)
class EvaluationScenarioEnvironment:
    database_engine: Engine
    session_factory: sessionmaker[Session]
    vector_client: ClientAPI
    embedding_provider: EvaluationEmbeddingProvider
    engineering_docs_collection: str
    tools: list[BaseTool]
    checkpoint_path: Path


@contextmanager
def open_evaluation_scenario_environment(
    working_directory: Path,
    fixture: ScenarioFixturePlan,
) -> Iterator[EvaluationScenarioEnvironment]:
    """Create one disposable environment for one evaluation scenario."""

    working_directory.mkdir(
        parents=True,
        exist_ok=True,
    )
    database_path = working_directory / "evaluation.sqlite"
    vector_store_path = working_directory / "chroma"
    checkpoint_path = working_directory / "checkpoints.sqlite"

    if database_path.exists():
        raise FileExistsError(f"Evaluation database already exists: {database_path}")

    database_engine = create_database_engine(f"sqlite+pysqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(database_engine)
    session_factory = sessionmaker(
        bind=database_engine,
        class_=Session,
        expire_on_commit=False,
    )
    vector_client = chromadb.PersistentClient(
        path=str(vector_store_path),
    )
    embedding_provider = EvaluationEmbeddingProvider()

    try:
        with session_factory() as database_session:
            assets = seed_reference_data(
                database_session,
                EVALUATION_REFERENCE_TIME,
            )
            seed_sensor_data(
                database_session,
                assets,
                EVALUATION_REFERENCE_TIME,
            )
            database_session.commit()

        index_engineering_documents(
            client=vector_client,
            embedding_provider=embedding_provider,
            documents_directory=Path("data/engineering_docs"),
            collection_name=EVALUATION_COLLECTION_NAME,
        )

        with session_factory() as database_session:
            apply_fixture_mutations(
                fixture.mutations,
                database_session=database_session,
                vector_client=vector_client,
                engineering_docs_collection=(EVALUATION_COLLECTION_NAME),
            )

        tools = build_investigation_tools(
            InvestigationToolDependencies(
                session_factory=session_factory,
                vector_client=vector_client,
                embedding_provider=embedding_provider,
                engineering_docs_collection=(EVALUATION_COLLECTION_NAME),
            )
        )

        yield EvaluationScenarioEnvironment(
            database_engine=database_engine,
            session_factory=session_factory,
            vector_client=vector_client,
            embedding_provider=embedding_provider,
            engineering_docs_collection=(EVALUATION_COLLECTION_NAME),
            tools=tools,
            checkpoint_path=checkpoint_path,
        )
    finally:
        database_engine.dispose()
