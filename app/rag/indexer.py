from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine

from app.core.config import get_settings
from app.rag.documents import load_engineering_document_chunks
from app.rag.embeddings import (
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)
from app.rag.vector_store import SQLVectorStore, VectorDocument


@dataclass(frozen=True)
class IndexSummary:
    collection_name: str
    source_document_count: int
    chunk_count: int


def index_engineering_documents(
    client: SQLVectorStore,
    embedding_provider: EmbeddingProvider,
    documents_directory: Path,
    collection_name: str,
) -> IndexSummary:
    chunks = load_engineering_document_chunks(documents_directory)
    embeddings = embedding_provider.embed_documents([chunk.content for chunk in chunks])

    if len(embeddings) != len(chunks):
        raise ValueError("Embedding count must match document chunk count.")

    documents = [
        VectorDocument(
            chunk_id=chunk.chunk_id,
            content=chunk.content,
            embedding=embedding,
            metadata={
                "document_id": chunk.document_id,
                "title": chunk.title,
                "section": chunk.section,
                "source_path": chunk.source_path,
                "applicable_assets": chunk.applicable_assets,
            },
        )
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]

    client.replace_collection(
        collection_name,
        documents,
        embedding_model=getattr(
            embedding_provider,
            "model_name",
            type(embedding_provider).__name__,
        ),
    )

    return IndexSummary(
        collection_name=collection_name,
        source_document_count=len({chunk.source_path for chunk in chunks}),
        chunk_count=len(chunks),
    )


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    try:
        client = SQLVectorStore(engine)
        embedding_provider = SentenceTransformerEmbeddingProvider(
            settings.embedding_model_name
        )
        summary = index_engineering_documents(
            client=client,
            embedding_provider=embedding_provider,
            documents_directory=Path(settings.engineering_docs_path),
            collection_name=settings.engineering_docs_collection,
        )

        print(f"Collection: {summary.collection_name}")
        print(f"Source documents: {summary.source_document_count}")
        print(f"Indexed chunks: {summary.chunk_count}")
        print(f"Embedding dimension: {embedding_provider.dimension}")
        print(f"Stored chunks: {client.count(summary.collection_name)}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()