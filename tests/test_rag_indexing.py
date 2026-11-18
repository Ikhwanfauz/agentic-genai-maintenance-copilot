from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.rag import RagChunk
from app.rag.documents import load_engineering_document_chunks
from app.rag.indexer import index_engineering_documents
from app.rag.vector_store import SQLVectorStore


class FakeEmbeddingProvider:
    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        return [
            [
                float(len(text)),
                float(text.lower().count("vibration") + 1),
                float(text.lower().count("approval") + 1),
            ]
            for text in texts
        ]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


def test_load_engineering_documents_creates_stable_chunks() -> None:
    chunks = load_engineering_document_chunks(Path("data/engineering_docs"))

    assert len(chunks) == 9
    assert len({chunk.chunk_id for chunk in chunks}) == 9

    elevated_vibration = next(
        chunk for chunk in chunks if chunk.chunk_id == "eng-pump-001-elevated-vibration"
    )

    assert elevated_vibration.document_id == "ENG-PUMP-001"
    assert elevated_vibration.section == "Elevated Vibration"
    assert elevated_vibration.source_path == "pump_troubleshooting_guide.md"
    assert "coupling misalignment" in elevated_vibration.content


def test_index_engineering_documents_is_idempotent() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    try:
        client = SQLVectorStore(engine)
        embedding_provider = FakeEmbeddingProvider()

        first_summary = index_engineering_documents(
            client=client,
            embedding_provider=embedding_provider,
            documents_directory=Path("data/engineering_docs"),
            collection_name="test_engineering_docs",
        )
        second_summary = index_engineering_documents(
            client=client,
            embedding_provider=embedding_provider,
            documents_directory=Path("data/engineering_docs"),
            collection_name="test_engineering_docs",
        )

        assert first_summary.source_document_count == 3
        assert first_summary.chunk_count == 9
        assert second_summary == first_summary
        assert client.count("test_engineering_docs") == 9

        with Session(engine) as session:
            stored_chunk = session.scalar(
                select(RagChunk).where(
                    RagChunk.collection_name == "test_engineering_docs",
                    RagChunk.chunk_id == "eng-pump-001-elevated-vibration",
                )
            )
            assert stored_chunk is not None
            assert stored_chunk.metadata_json["document_id"] == "ENG-PUMP-001"
            assert "coupling misalignment" in stored_chunk.content
            assert stored_chunk.embedding_dimension == 3
    finally:
        engine.dispose()
