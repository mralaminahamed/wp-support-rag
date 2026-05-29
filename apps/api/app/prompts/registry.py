"""Versioned prompt registry (ADR-005, FR-GN-2).

Prompts are immutable, versioned code, not strings in env or a database. Each
family is a set of :class:`PromptVersion` definitions with exactly one ``active``
version resolved at runtime. Promoting or rolling back is a reviewed code change.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

from app.rag.retriever import RetrievedChunk

PromptStatus = Literal["active", "candidate", "retired"]


@dataclass(frozen=True)
class PromptVersion:
    """An immutable, versioned prompt definition.

    Attributes:
        family: Logical prompt family (for example ``"support_answer"``).
        version: Monotonic version string (for example ``"2026.05.0"``).
        status: One of ``"active"``, ``"candidate"``, or ``"retired"``.
        system: System prompt text.
        render: Callable rendering the user message from question + chunks.
        changelog: Human-readable note describing what changed and why.
    """

    family: str
    version: str
    status: PromptStatus
    system: str
    render: Callable[[str, Sequence[RetrievedChunk]], str]
    changelog: str


@dataclass
class PromptRegistry:
    """An in-memory registry of prompt versions keyed by family."""

    _families: dict[str, list[PromptVersion]] = field(default_factory=dict)

    def register(self, version: PromptVersion) -> None:
        """Register a prompt version.

        Args:
            version: The version to register.

        Raises:
            ValueError: If a second ``active`` version is registered for a family.
        """
        versions = self._families.setdefault(version.family, [])
        if version.status == "active" and any(v.status == "active" for v in versions):
            raise ValueError(f"family {version.family!r} already has an active version")
        versions.append(version)

    def active(self, family: str) -> PromptVersion:
        """Return the active version of a family (FR-GN-2).

        Args:
            family: The prompt family.

        Returns:
            PromptVersion: The active version.

        Raises:
            KeyError: If the family is unknown or has no active version.
        """
        for version in self._families.get(family, []):
            if version.status == "active":
                return version
        raise KeyError(f"no active version for family {family!r}")

    def get(self, family: str, version: str) -> PromptVersion:
        """Return a specific version of a family.

        Args:
            family: The prompt family.
            version: The version string.

        Returns:
            PromptVersion: The matching version.

        Raises:
            KeyError: If no such version exists.
        """
        for candidate in self._families.get(family, []):
            if candidate.version == version:
                return candidate
        raise KeyError(f"no version {version!r} for family {family!r}")


@lru_cache(maxsize=1)
def get_registry() -> PromptRegistry:
    """Return the process-wide prompt registry with all families loaded.

    Returns:
        PromptRegistry: The populated registry.
    """
    registry = PromptRegistry()
    from app.prompts.families import support_answer

    for version in support_answer.VERSIONS:
        registry.register(version)
    return registry
