import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DataError

from app.core.config import get_settings
from app.models.rag import RagChunk, RagCollection
from app.rag.vector_store import SQLVectorStore, VectorDocument
from app.tools.exceptions import VectorStoreNotReadyError

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_POSTGRES_TESTS") != "1",
    reason="Set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests.",
)


@pytest.fixture
def postgres_store():
    source_url = make_url(get_settings().database_url)
    if source_url.get_backend_name() != "postgresql":
        pytest.fail("PostgreSQL integration tests require a PostgreSQL DATABASE_URL.")

    test_url = source_url.set(database="maintenance_copilot_test")
    engine = create_engine(test_url, pool_pre_ping=True)
    collection_name = f"pytest_{uuid4().hex}"

    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            RagCollection.__table__.create(connection, checkfirst=True)
            RagChunk.__table__.create(connection, checkfirst=True)

        yield SQLVectorStore(engine), collection_name
    finally:
        try:
            with engine.begin() as connection:
                connection.execute(
                    delete(RagChunk).where(RagChunk.collection_name == collection_name)
                )
                connection.execute(
                    delete(RagCollection).where(RagCollection.name == collection_name)
                )
        finally:
            engine.dispose()


def documents() -> list[VectorDocument]:
    return [
        VectorDocument(
            chunk_id="near",
            content="Pump vibration guidance.",
            metadata={"document_id": "DOC-1", "section": "Vibration"},
            embedding=[0.0, 0.0, 0.0],
        ),
        VectorDocument(
            chunk_id="far",
            content="Maintenance approval guidance.",
            metadata={"document_id": "DOC-2", "section": "Approval"},
            embedding=[3.0, 4.0, 0.0],
        ),
    ]


def test_postgres_search_preserves_metadata_and_squared_distance(postgres_store):
    store, name = postgres_store
    store.replace_collection(name, documents(), embedding_model="test-model")

    matches = store.search(name, [0.0, 0.0, 0.0], limit=2)

    assert [match.chunk_id for match in matches] == ["near", "far"]
    assert matches[0].distance == pytest.approx(0.0)
    assert matches[1].distance == pytest.approx(25.0)
    assert matches[0].content == "Pump vibration guidance."
    assert matches[0].metadata == {
        "document_id": "DOC-1",
        "section": "Vibration",
    }


def test_postgres_reindex_replaces_collection_without_duplicates(postgres_store):
    store, name = postgres_store
    store.replace_collection(name, documents(), embedding_model="test-model")
    store.replace_collection(name, documents(), embedding_model="test-model")
    assert store.count(name) == 2

    store.replace_collection(
        name,
        documents()[:1],
        embedding_model="test-model",
    )

    assert store.count(name) == 1
    assert store.search(name, [0.0, 0.0, 0.0], limit=2)[0].chunk_id == "near"


def test_postgres_failed_reindex_rolls_back_existing_documents(postgres_store):
    store, name = postgres_store
    store.replace_collection(name, documents(), embedding_model="test-model")
    invalid_document = VectorDocument(
        chunk_id="x" * 256,
        content="This exceeds the chunk ID column limit.",
        metadata={},
        embedding=[1.0, 0.0, 0.0],
    )

    with pytest.raises(DataError):
        store.replace_collection(
            name,
            [invalid_document],
            embedding_model="test-model",
        )

    assert store.count(name) == 2
    assert [match.chunk_id for match in store.search(name, [0.0, 0.0, 0.0], limit=2)] == [
        "near",
        "far",
    ]


def test_postgres_rejects_wrong_query_dimension(postgres_store):
    store, name = postgres_store
    store.replace_collection(name, documents(), embedding_model="test-model")

    with pytest.raises(ValueError, match="dimension"):
        store.search(name, [1.0, 0.0], limit=1)

    assert store.count(name) == 2


def test_postgres_empty_collection_raises_not_ready(postgres_store):
    store, name = postgres_store

    with pytest.raises(VectorStoreNotReadyError):
        store.search(name, [0.0, 0.0, 0.0], limit=1)

    store.replace_collection(name, documents(), embedding_model="test-model")
    store.clear(name)

    assert store.count(name) == 0
    with pytest.raises(VectorStoreNotReadyError):
        store.search(name, [0.0, 0.0, 0.0], limit=1)
