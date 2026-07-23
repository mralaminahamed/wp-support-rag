"""LangChain ``PGVectorStore`` — dynamically-created vectors schema.

Follows the langchain-postgres convention where LangChain owns and creates the
vectors table (``ainit_vectorstore_table``) rather than binding to the legacy
hand-rolled ``chunks`` table. The store performs hybrid (dense + full-text)
retrieval with Reciprocal Rank Fusion in the database, mirroring the legacy
RRF weighting via ``rrf_k``.

Because dynamic creation stores embeddings in a pgvector ``vector`` column
(HNSW-indexable only up to 2000 dims), this path requires an embedding width
<= 2000 — enforced by ``Settings`` when ``use_langchain`` is on. See the
LangChain migration spec under ``docs/superpowers/specs``.

Gated by ``settings.use_langchain``; unused while the flag is off.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_postgres import Column, PGEngine, PGVectorStore
from langchain_postgres.v2.hybrid_search_config import (
    HybridSearchConfig,
    reciprocal_rank_fusion,
)
from langchain_postgres.v2.indexes import HNSWIndex, HNSWQueryOptions
from sqlalchemy.exc import ProgrammingError

from app.config import Settings
from app.db.engine import get_engine
from app.rag.embeddings import WpragEmbeddings

logger = logging.getLogger(__name__)

LC_TABLE = "lc_chunks"
"""Table LangChain creates and owns for chunk embeddings + hybrid search."""

HNSW_INDEX_NAME = "lc_chunks_embedding_hnsw"
"""Name of the HNSW index applied to the embedding column (parity with legacy)."""

# Cache the built store per (dimensions, provider) so a PGVectorStore — and its
# engine wrapper — is not rebuilt on every request. Guarded by an async lock.
_store_cache: dict[tuple[int, str], PGVectorStore] = {}
_store_lock = asyncio.Lock()


def _pg_engine() -> PGEngine:
    """Wrap the process-wide async engine for langchain-postgres."""
    return PGEngine.from_engine(get_engine())


def _hybrid_config(settings: Settings) -> HybridSearchConfig:
    """Build the hybrid-search config: full-text column + RRF fusion.

    Args:
        settings: Application settings supplying ``rrf_k`` and candidate depth.

    Returns:
        HybridSearchConfig: Dense + FTS fusion via ``reciprocal_rank_fusion``.
    """
    return HybridSearchConfig(
        tsv_column="content_tsv",
        tsv_lang="pg_catalog.english",
        fusion_function=reciprocal_rank_fusion,
        fusion_function_parameters={
            "rrf_k": settings.rrf_k,
            "fetch_top_k": settings.retrieval_top_n,
        },
        primary_top_k=settings.retrieval_top_n,
        secondary_top_k=settings.retrieval_top_n,
    )


def _metadata_columns() -> list[Any]:
    """Real, filterable metadata columns on the created table.

    Typed as ``list[Any]`` because ``ainit_vectorstore_table`` accepts a
    ``list[Column | ColumnDict]`` (invariant), which a ``list[Column]`` cannot
    satisfy directly.
    """
    return [
        Column("plugin_id", "UUID"),
        Column("document_id", "UUID"),
        Column("heading_path", "TEXT"),
        Column("source_url", "TEXT"),
    ]


async def init_vectorstore_schema(settings: Settings) -> None:
    """Idempotently create the LangChain vectors table + HNSW index.

    Safe to call on every boot: an existing table raises ``ProgrammingError``,
    which is swallowed. Applying the HNSW index is also idempotent (skipped when
    it already exists). Called from the app lifespan when ``use_langchain`` is on.

    Args:
        settings: Application settings (vector width, RRF, ef_search).
    """
    engine = _pg_engine()
    try:
        await engine.ainit_vectorstore_table(
            table_name=LC_TABLE,
            vector_size=settings.embedding_dimensions,
            id_column=Column("id", "UUID"),
            content_column="content",
            embedding_column="embedding",
            metadata_columns=_metadata_columns(),
            metadata_json_column="metadata",
            hybrid_search_config=_hybrid_config(settings),
            store_metadata=True,
        )
        logger.info("created langchain vectors table", extra={"table": LC_TABLE})
    except ProgrammingError:
        logger.debug("langchain vectors table already exists", extra={"table": LC_TABLE})

    store = await _build_store(settings)
    try:
        await store.aapply_vector_index(
            HNSWIndex(name=HNSW_INDEX_NAME, m=16, ef_construction=64)
        )
        logger.info("applied HNSW index", extra={"index": HNSW_INDEX_NAME})
    except Exception:  # noqa: BLE001 - index may already exist; non-fatal at boot
        logger.debug("HNSW index already present or not applied", extra={"index": HNSW_INDEX_NAME})


async def _build_store(settings: Settings) -> PGVectorStore:
    """Construct a ``PGVectorStore`` bound to the created table.

    Args:
        settings: Application settings (ef_search, RRF, embedding width).

    Returns:
        PGVectorStore: Store configured for hybrid search + cosine distance.
    """
    return await PGVectorStore.create(
        engine=_pg_engine(),
        embedding_service=WpragEmbeddings(settings),
        table_name=LC_TABLE,
        id_column="id",
        content_column="content",
        embedding_column="embedding",
        metadata_columns=["plugin_id", "document_id", "heading_path", "source_url"],
        metadata_json_column="metadata",
        index_query_options=HNSWQueryOptions(ef_search=settings.ef_search),
        hybrid_search_config=_hybrid_config(settings),
    )


async def get_vectorstore(settings: Settings) -> PGVectorStore:
    """Return a cached ``PGVectorStore`` for the active embedding config.

    Keyed on (embedding width, embedding provider) so a config change rebuilds
    the store. Thread-safe under asyncio via a module lock.

    Args:
        settings: Application settings.

    Returns:
        PGVectorStore: The (possibly cached) store.
    """
    key = (settings.embedding_dimensions, settings.embedding_provider)
    cached = _store_cache.get(key)
    if cached is not None:
        return cached
    async with _store_lock:
        cached = _store_cache.get(key)
        if cached is None:
            cached = await _build_store(settings)
            _store_cache[key] = cached
        return cached
