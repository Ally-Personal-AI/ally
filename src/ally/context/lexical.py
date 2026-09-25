"""Shared deterministic lexical scoring for local retrieval."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from math import log

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

_BM25_K1 = 1.2
_BM25_B = 0.75


def lexical_terms(value: str) -> tuple[str, ...]:
    """Return normalized ordered terms while preserving repeated occurrences."""

    return tuple(
        token
        for token in (match.group(0).lower() for match in _TOKEN_PATTERN.finditer(value))
        if token not in _STOP_WORDS
    )


def lexical_tokens(value: str) -> frozenset[str]:
    """Return normalized unique content tokens for deterministic matching."""

    return frozenset(lexical_terms(value))


def bm25_scores(query: str, documents: Sequence[str]) -> tuple[float, ...]:
    """Score documents with deterministic BM25 relevance and no external state."""

    if not documents:
        return ()

    query_terms = lexical_tokens(query)
    document_terms = tuple(lexical_terms(document) for document in documents)
    if not query_terms:
        return tuple(0.0 for _ in document_terms)

    document_count = len(document_terms)
    total_terms = sum(len(terms) for terms in document_terms)
    if total_terms == 0:
        return tuple(0.0 for _ in document_terms)
    average_document_length = total_terms / document_count

    document_frequency: Counter[str] = Counter()
    for terms in document_terms:
        document_frequency.update(set(terms))

    inverse_document_frequency = {
        term: log(
            1.0
            + (
                document_count
                - document_frequency.get(term, 0)
                + 0.5
            )
            / (document_frequency.get(term, 0) + 0.5)
        )
        for term in query_terms
    }

    scores: list[float] = []
    for terms in document_terms:
        frequencies = Counter(terms)
        document_length = len(terms)
        length_normalization = _BM25_K1 * (
            1.0
            - _BM25_B
            + _BM25_B * document_length / average_document_length
        )
        score = 0.0
        for term in query_terms:
            frequency = frequencies.get(term, 0)
            if frequency == 0:
                continue
            score += inverse_document_frequency[term] * (
                frequency * (_BM25_K1 + 1.0)
                / (frequency + length_normalization)
            )
        scores.append(score)
    return tuple(scores)
