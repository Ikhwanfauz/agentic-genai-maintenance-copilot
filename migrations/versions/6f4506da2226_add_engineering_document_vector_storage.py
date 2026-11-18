"""Add engineering document vector storage."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "6f4506da2226"
down_revision: str | Sequence[str] | None = "0e66bfb68f1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    dialect = op.get_bind().dialect.name

    if dialect == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "rag_collections",
        sa.Column("name", sa.String(255), primary_key=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("embedding_model", sa.String(255), nullable=True),
        sa.CheckConstraint(
            "embedding_dimension > 0",
            name="ck_rag_collections_dimension_positive",
        ),
        sa.UniqueConstraint(
            "name",
            "embedding_dimension",
            name="uq_rag_collections_name_dimension",
        ),
    )

    constraints = [
        sa.CheckConstraint(
            "embedding_dimension > 0",
            name="ck_rag_chunks_dimension_positive",
        ),
        sa.ForeignKeyConstraint(
            ["collection_name", "embedding_dimension"],
            ["rag_collections.name", "rag_collections.embedding_dimension"],
            name="fk_rag_chunks_collection_dimension",
            ondelete="CASCADE",
        ),
    ]

    if dialect == "postgresql":
        constraints.append(
            sa.CheckConstraint(
                "vector_dims(embedding) = embedding_dimension",
                name="ck_rag_chunks_embedding_dimension",
            )
        )

    op.create_table(
        "rag_chunks",
        sa.Column("collection_name", sa.String(255), primary_key=True),
        sa.Column("chunk_id", sa.String(255), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("embedding_dimension", sa.Integer(), nullable=False),
        sa.Column(
            "embedding",
            VECTOR().with_variant(sa.JSON(), "sqlite"),
            nullable=False,
        ),
        *constraints,
    )


def downgrade() -> None:
    op.drop_table("rag_chunks")
    op.drop_table("rag_collections")
