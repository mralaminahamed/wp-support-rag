"""Ingestion result model.

A small Pydantic model describing the outcome of ingesting a single source,
returned by the ingestion task and surfaced via the admin API in later phases.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

RunStatus = Literal["succeeded", "failed"]


class IngestSummary(BaseModel):
    """Outcome of ingesting one source.

    Attributes:
        source_id: The ingested source id.
        source_type: The source type ingested.
        status: Terminal run status.
        documents_new: Count of newly inserted documents.
        documents_updated: Count of documents whose content changed.
        documents_unchanged: Count of documents skipped by content hash (FR-IN-5).
        error: Failure detail when ``status`` is ``failed``.
    """

    source_id: uuid.UUID
    source_type: str
    status: RunStatus
    documents_new: int = 0
    documents_updated: int = 0
    documents_unchanged: int = 0
    error: str | None = None
