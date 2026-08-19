from dataclasses import dataclass
from pathlib import Path

import chromadb
from chromadb.api import ClientAPI

from app.core.config import get_settings
from app.rag.documents import load_engineering_document_chunks
from app.rag.embeddings import (
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
)


@dataclass(frozen=True)
class IndexSummary:
    collection_name: str
    source_document_count: int
    chunk_count: int


def index_engineering_documents(
    client: ClientAPI,
    embedding_provider: EmbeddingProvider,
    documents_directory: Path,
    collection_name: str,
) -> IndexSummary:
    chunks = load_engineering_document_chunks(documents_directory)
    embeddings = embedding_provider.embed_documents([chunk.content for chunk in chunks])

    if len(embeddings) != len(chunks):
        raise ValueError("Embedding count must match document chunk count.")

    collection = client.get_or_create_collection(
        name=collection_name,
    )

    collection.upsert(
        ids=[chunk.chunk_id for chunk in chunks],
        documents=[chunk.content for chunk in chunks],
        embeddings=embeddings,
        metadatas=[
            {
                "document_id": chunk.document_id,
                "title": chunk.title,
                "section": chunk.section,
                "source_path": chunk.source_path,
                "applicable_assets": chunk.applicable_assets,
            }
            for chunk in chunks
        ],
    )

    return IndexSummary(
        collection_name=collection_name,
        source_document_count=len({chunk.source_path for chunk in chunks}),
        chunk_count=len(chunks),
    )


def main() -> None:
    settings = get_settings()
    vector_store_path = Path(settings.vector_store_path)
    vector_store_path.mkdir(
        parents=True,
        exist_ok=True,
    )

    client = chromadb.PersistentClient(
        path=str(vector_store_path),
    )
    embedding_provider = SentenceTransformerEmbeddingProvider(settings.embedding_model_name)

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


if __name__ == "__main__":
    main()
