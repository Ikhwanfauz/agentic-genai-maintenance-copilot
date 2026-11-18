from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RagCollection(Base):
    __tablename__ = "rag_collections"
    __table_args__ = (
        CheckConstraint(
            "embedding_dimension > 0",
            name="ck_rag_collections_dimension_positive",
        ),
        UniqueConstraint(
            "name",
            "embedding_dimension",
            name="uq_rag_collections_name_dimension",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), primary_key=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer)
    embedding_model: Mapped[str | None] = mapped_column(String(255))


class RagChunk(Base):
    __tablename__ = "rag_chunks"
    __table_args__ = (
        CheckConstraint(
            "embedding_dimension > 0",
            name="ck_rag_chunks_dimension_positive",
        ),
        ForeignKeyConstraint(
            ["collection_name", "embedding_dimension"],
            ["rag_collections.name", "rag_collections.embedding_dimension"],
            name="fk_rag_chunks_collection_dimension",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "vector_dims(embedding) = embedding_dimension",
            name="ck_rag_chunks_embedding_dimension",
        ).ddl_if(dialect="postgresql"),
    )

    collection_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        VECTOR().with_variant(JSON(), "sqlite"),
        nullable=False,
    )
