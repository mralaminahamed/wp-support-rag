"""Evaluation metrics (FR-EV-2).

Pure, deterministic scorers used by the harness: context recall, citation
accuracy, answer faithfulness, and answer edit distance against the reference.
All functions are side-effect free so the harness can aggregate them offline.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

from collections.abc import Sequence


def normalized_edit_distance(a: str, b: str) -> float:
    """Return the Levenshtein distance between two strings, normalised to [0, 1].

    Args:
        a: First string.
        b: Second string.

    Returns:
        float: ``levenshtein(a, b) / max(len(a), len(b))``; 0.0 if both are empty.
    """
    if not a and not b:
        return 0.0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            cost = 0 if ca == cb else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1] / max(len(a), len(b))


def answer_similarity(answer: str, reference: str) -> float:
    """Return 1 minus the normalised edit distance between answer and reference.

    Args:
        answer: The generated answer.
        reference: The reference answer.

    Returns:
        float: Similarity in [0, 1]; 1.0 means identical.
    """
    return 1.0 - normalized_edit_distance(answer, reference)


def source_in_results(expected_substrings: Sequence[str], urls: Sequence[str]) -> bool:
    """Report whether any URL contains every expected substring (context recall).

    Args:
        expected_substrings: Substrings the expected source URL must contain.
        urls: Source URLs of retrieved chunks.

    Returns:
        bool: ``True`` if some URL contains all expected substrings.
    """
    if not expected_substrings:
        return False
    return any(all(sub in url for sub in expected_substrings) for url in urls)


def citation_is_accurate(expected_substrings: Sequence[str], citations: Sequence[str]) -> bool:
    """Report whether a cited URL matches the expected source (citation accuracy).

    Args:
        expected_substrings: Substrings the expected source URL must contain.
        citations: URLs cited in the generated answer.

    Returns:
        bool: ``True`` if some citation contains all expected substrings.
    """
    return source_in_results(expected_substrings, citations)


def is_faithful(citations: Sequence[str], supplied_urls: Sequence[str]) -> bool:
    """Report whether every citation comes from a supplied chunk (no fabrication).

    Args:
        citations: URLs cited in the generated answer.
        supplied_urls: Source URLs of chunks supplied to the model.

    Returns:
        bool: ``True`` if all citations are a subset of the supplied URLs.
    """
    allowed = set(supplied_urls)
    return all(citation in allowed for citation in citations)
