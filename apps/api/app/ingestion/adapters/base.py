"""Source adapter contract — re-exported from wp_support_rag_sdk.

All adapter implementations and the ingestion pipeline import from here.
External adapter developers import from wp_support_rag_sdk directly.

Author: Al Amin Ahamed.
"""
from __future__ import annotations

from wp_support_rag_sdk.adapter import (
    ContentType,
    RawDocument,
    SourceAdapter,
    SourceContext,
    SourceFetchError,
)

__all__ = [
    "ContentType",
    "RawDocument",
    "SourceAdapter",
    "SourceContext",
    "SourceFetchError",
]
