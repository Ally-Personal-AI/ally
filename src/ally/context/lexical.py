"""Shared deterministic lexical tokenization for local retrieval."""

from __future__ import annotations

import re

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "i",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "what",
        "with",
        "you",
    }
)


def lexical_tokens(value: str) -> frozenset[str]:
    """Return normalized content tokens suitable for deterministic overlap ranking."""

    return frozenset(
        token
        for token in (match.group(0).lower() for match in _TOKEN_PATTERN.finditer(value))
        if token not in _STOP_WORDS
    )
