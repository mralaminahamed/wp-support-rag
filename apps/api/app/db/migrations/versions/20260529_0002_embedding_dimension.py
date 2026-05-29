"""Re-dimension the chunk embedding column to the configured provider width.

The embedding dimension is bound to the ``chunks.embedding`` column and its HNSW
index (ADR-002). Switching the embedding provider — e.g. OpenAI's 3072-dim
``text-embedding-3-large`` to a local Ollama model's native width — changes that
dimension, so the column type and index must move together. Existing vectors are
of the old width and cannot be reinterpreted, so this migration clears the chunk
table; the corpus is re-embedded by re-running ingestion afterwards (FR-PR-7).

The target type comes from :func:`embedding_type`, which reads configuration, so
the column always matches the active provider at upgrade time.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from alembic import op
from app.db.models import HNSW_OPS, embedding_type

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: None = None
depends_on: None = None


def upgrade() -> None:
    """Re-create the embedding column at the configured dimension and rebuild HNSW."""
    # Old vectors are of the previous width; clear them so re-ingestion repopulates
    # at the new dimension. Centroids are cached in Redis and recomputed on ingest.
    op.execute("TRUNCATE TABLE chunks")
    op.drop_index("chunks_embedding_hnsw", table_name="chunks")
    op.alter_column(
        "chunks",
        "embedding",
        type_=embedding_type(),
        existing_nullable=False,
        postgresql_using="NULL",
    )
    op.create_index(
        "chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": HNSW_OPS},
    )


def downgrade() -> None:
    """Restore the default OpenAI ``halfvec(3072)`` embedding column.

    Like the upgrade, this clears chunks because stored vectors cannot change
    width in place.
    """
    from pgvector.sqlalchemy import HALFVEC

    op.execute("TRUNCATE TABLE chunks")
    op.drop_index("chunks_embedding_hnsw", table_name="chunks")
    op.alter_column(
        "chunks",
        "embedding",
        type_=HALFVEC(3072),
        existing_nullable=False,
        postgresql_using="NULL",
    )
    op.create_index(
        "chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "halfvec_cosine_ops"},
    )
