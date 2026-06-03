"""Switch chunk embedding column to halfvec(2560) for qwen3-embedding:4b.

Drops the old HNSW index, alters the column from halfvec(768) to halfvec(2560),
clears existing 768-dim vectors (incompatible — must re-ingest), then recreates
the HNSW index at the new width.

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-02

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260602_0008"
down_revision: str | None = "20260602_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Drop dependent HNSW index first (cannot ALTER column with active index).
    op.drop_index("chunks_embedding_hnsw", table_name="chunks")

    # 2. Clear stale 768-dim vectors — they cannot be reinterpreted at 2560 dims.
    op.execute("TRUNCATE TABLE chunks RESTART IDENTITY")

    # 3. Alter column to halfvec(2560).
    op.execute(
        "ALTER TABLE chunks ALTER COLUMN embedding TYPE halfvec(2560) "
        "USING embedding::text::halfvec(2560)"
    )

    # 4. Recreate HNSW index for cosine similarity at 2560 dims.
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.drop_index("chunks_embedding_hnsw", table_name="chunks")
    op.execute("TRUNCATE TABLE chunks RESTART IDENTITY")
    op.execute(
        "ALTER TABLE chunks ALTER COLUMN embedding TYPE halfvec(768) "
        "USING embedding::text::halfvec(768)"
    )
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding halfvec_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )
