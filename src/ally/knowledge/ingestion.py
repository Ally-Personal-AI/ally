"""Deterministic knowledge ingestion services."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ally.knowledge import KnowledgeRevision, KnowledgeSource, KnowledgeStore, NewKnowledgeSource
from ally.knowledge.chunking import chunk_text


def text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class TextKnowledgeIngestor:
    """Ingest UTF-8 text while preserving file provenance and revisions."""

    def __init__(self, store: KnowledgeStore) -> None:
        self._store = store

    def ingest_text(
        self,
        *,
        uri: str,
        title: str,
        text: str,
        media_type: str = "text/plain",
    ) -> tuple[KnowledgeSource, KnowledgeRevision]:
        chunks = chunk_text(text)
        if not chunks:
            raise ValueError("knowledge source contains no non-whitespace text")

        return self._store.ingest(
            NewKnowledgeSource(uri=uri, title=title, media_type=media_type),
            source_sha256=text_sha256(text),
            chunks=chunks,
        )

    def ingest_file(self, path: Path) -> tuple[KnowledgeSource, KnowledgeRevision]:
        resolved = path.expanduser().resolve()
        if not resolved.is_file():
            raise ValueError(f"Not a file: {resolved}")

        try:
            text = resolved.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                "Knowledge V1 supports UTF-8 plain-text files only."
            ) from exc

        return self.ingest_text(
            uri=resolved.as_uri(),
            title=resolved.name,
            text=text,
        )
