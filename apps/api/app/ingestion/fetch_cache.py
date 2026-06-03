"""Disk cache for pre-fetched raw documents and processed chunks.

Stores RawDocument JSON and ChunkData JSONL per (source_id, external_id) so
the ingestion pipeline can skip HTTP and re-chunking on subsequent runs.

Layout::

    {root}/
      {source_id}/
        {safe_external_id}.raw.json      # RawDocument serialised as JSON
        {safe_external_id}.chunks.jsonl  # one ChunkData JSON per line

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.ingestion.adapters.base import RawDocument
from app.processing.chunker import ChunkData

_UNSAFE = re.compile(r"[^\w.:@-]")


def _safe(name: str) -> str:
    return _UNSAFE.sub("_", name)[:200]


class FetchCache:
    """File-based RawDocument + ChunkData cache keyed by (source_id, external_id)."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    # ------------------------------------------------------------------
    # Paths
    # ------------------------------------------------------------------

    def raw_path(self, source_id: str, external_id: str) -> Path:
        return self.root / source_id / f"{_safe(external_id)}.raw.json"

    def chunks_path(self, source_id: str, external_id: str) -> Path:
        return self.root / source_id / f"{_safe(external_id)}.chunks.jsonl"

    # ------------------------------------------------------------------
    # Raw documents
    # ------------------------------------------------------------------

    def has_raw(self, source_id: str, external_id: str) -> bool:
        return self.raw_path(source_id, external_id).exists()

    def save_raw(self, source_id: str, raw: RawDocument) -> None:
        path = self.raw_path(source_id, raw.external_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw.model_dump_json(), encoding="utf-8")

    def load_raw(self, source_id: str, external_id: str) -> RawDocument | None:
        path = self.raw_path(source_id, external_id)
        if not path.exists():
            return None
        return RawDocument.model_validate_json(path.read_text(encoding="utf-8"))

    def list_raw(self, source_id: str) -> list[RawDocument]:
        """Return all cached RawDocuments for a source."""
        source_dir = self.root / source_id
        if not source_dir.exists():
            return []
        docs = []
        for f in sorted(source_dir.glob("*.raw.json")):
            try:
                docs.append(RawDocument.model_validate_json(f.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                pass
        return docs

    # ------------------------------------------------------------------
    # Chunks
    # ------------------------------------------------------------------

    def has_chunks(self, source_id: str, external_id: str) -> bool:
        return self.chunks_path(source_id, external_id).exists()

    def save_chunks(self, source_id: str, external_id: str, chunks: list[ChunkData]) -> None:
        path = self.chunks_path(source_id, external_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(c.model_dump_json() for c in chunks),
            encoding="utf-8",
        )

    def load_chunks(self, source_id: str, external_id: str) -> list[ChunkData]:
        path = self.chunks_path(source_id, external_id)
        if not path.exists():
            return []
        return [
            ChunkData.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, int]:
        if not self.root.exists():
            return {"sources": 0, "raw_docs": 0, "chunk_files": 0}
        sources = raw_docs = chunk_files = 0
        for source_dir in self.root.iterdir():
            if not source_dir.is_dir():
                continue
            sources += 1
            for f in source_dir.iterdir():
                if f.name.endswith(".raw.json"):
                    raw_docs += 1
                elif f.suffix == ".jsonl":
                    chunk_files += 1
        return {"sources": sources, "raw_docs": raw_docs, "chunk_files": chunk_files}
