"""Deterministic plain-text chunking with source offsets."""

from __future__ import annotations

import hashlib

from ally.knowledge.models import NewKnowledgeChunk


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def chunk_text(
    text: str,
    *,
    max_chars: int = 1600,
    overlap_chars: int = 200,
) -> tuple[NewKnowledgeChunk, ...]:
    """Split text into bounded overlapping chunks while preserving offsets."""

    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be non-negative and smaller than max_chars")
    if not text.strip():
        return ()

    chunks: list[NewKnowledgeChunk] = []
    start = 0
    ordinal = 0
    length = len(text)

    while start < length:
        target_end = min(start + max_chars, length)
        end = target_end

        if target_end < length:
            boundary = text.rfind("\n", start + (max_chars // 2), target_end)
            if boundary < 0:
                boundary = text.rfind(" ", start + (max_chars // 2), target_end)
            if boundary > start:
                end = boundary

        raw = text[start:end]
        left_trim = len(raw) - len(raw.lstrip())
        right_trim = len(raw) - len(raw.rstrip())
        chunk_start = start + left_trim
        chunk_end = end - right_trim

        if chunk_end > chunk_start:
            content = text[chunk_start:chunk_end]
            chunks.append(
                NewKnowledgeChunk(
                    ordinal=ordinal,
                    content=content,
                    start_char=chunk_start,
                    end_char=chunk_end,
                    sha256=_sha256(content),
                )
            )
            ordinal += 1

        if end >= length:
            break

        next_start = max(end - overlap_chars, start + 1)
        while next_start < length and text[next_start].isspace():
            next_start += 1
        start = next_start

    return tuple(chunks)
