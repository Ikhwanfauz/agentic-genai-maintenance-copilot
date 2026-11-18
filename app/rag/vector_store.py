import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.models.rag import RagChunk, RagCollection
from app.tools.exceptions import VectorStoreNotReadyError


@dataclass(frozen=True)
class VectorDocument:
    chunk_id: str
    content: str
    metadata: dict[str, Any]
    embedding: list[float]


@dataclass(frozen=True)
class VectorMatch:
    chunk_id: str
    content: str
    metadata: dict[str, Any]
    distance: float


def validate_vector(vector: Sequence[float], dimension: int) -> None:
    if len(vector) != dimension or dimension < 1:
        raise ValueError("Embedding dimension does not match the collection.")
    if not all(math.isfinite(value) for value in vector):
        raise ValueError("Embeddings must contain finite numbers.")


class SQLVectorStore:
    def __init__(self, engine: Engine) -> None:
        if engine.dialect.name not in {"postgresql", "sqlite"}:
            raise ValueError("Unsupported vector-store database.")
        self.engine = engine

    def replace_collection(
        self,
        name: str,
        documents: Sequence[VectorDocument],
        *,
        embedding_model: str,
    ) -> None:
        if not documents:
            raise ValueError("Cannot index an empty document collection.")
        if len({document.chunk_id for document in documents}) != len(documents):
            raise ValueError("Chunk IDs must be unique within a collection.")

        dimension = len(documents[0].embedding)
        for document in documents:
            validate_vector(document.embedding, dimension)

        with Session(self.engine) as session, session.begin():
            collection = session.scalar(
                select(RagCollection)
                .where(RagCollection.name == name)
                .with_for_update()
            )
            if collection is None:
                collection = RagCollection(name=name)
                session.add(collection)
                session.flush()

            session.execute(
                delete(RagChunk).where(RagChunk.collection_name == name)
            )
            collection.embedding_dimension = dimension
            collection.embedding_model = embedding_model
            session.flush()

            session.add_all(
                [
                    RagChunk(
                        collection_name=name,
                        chunk_id=document.chunk_id,
                        content=document.content,
                        metadata_json=document.metadata,
                        embedding_dimension=dimension,
                        embedding=document.embedding,
                    )
                    for document in documents
                ]
            )

    def count(self, name: str) -> int:
        with Session(self.engine) as session:
            return session.scalar(
                select(func.count())
                .select_from(RagChunk)
                .where(RagChunk.collection_name == name)
            ) or 0

    def clear(self, name: str) -> None:
        with Session(self.engine) as session, session.begin():
            session.execute(
                delete(RagChunk).where(RagChunk.collection_name == name)
            )

    def search(
        self,
        name: str,
        query_embedding: Sequence[float],
        limit: int,
    ) -> list[VectorMatch]:
        if limit < 1:
            raise ValueError("Search limit must be positive.")

        with Session(self.engine) as session:
            collection = session.get(RagCollection, name)
            if collection is None or collection.embedding_dimension is None:
                raise VectorStoreNotReadyError(name)
            validate_vector(query_embedding, collection.embedding_dimension)

            if self.engine.dialect.name == "postgresql":
                distance = RagChunk.embedding.l2_distance(list(query_embedding))
                rows = session.execute(
                    select(RagChunk, distance.label("distance"))
                    .where(RagChunk.collection_name == name)
                    .order_by(distance, RagChunk.chunk_id)
                    .limit(limit)
                ).all()
                matches = [
                    VectorMatch(
                        chunk_id=chunk.chunk_id,
                        content=chunk.content,
                        metadata=chunk.metadata_json,
                        distance=float(value) ** 2,
                    )
                    for chunk, value in rows
                ]
            else:
                chunks = session.scalars(
                    select(RagChunk).where(RagChunk.collection_name == name)
                ).all()
                matches = [
                    VectorMatch(
                        chunk_id=chunk.chunk_id,
                        content=chunk.content,
                        metadata=chunk.metadata_json,
                        distance=sum(
                            (left - right) ** 2
                            for left, right in zip(
                                chunk.embedding,
                                query_embedding,
                                strict=True,
                            )
                        ),
                    )
                    for chunk in chunks
                ]
                matches.sort(key=lambda match: (match.distance, match.chunk_id))
                matches = matches[:limit]

            if not matches:
                raise VectorStoreNotReadyError(name)
            return matches