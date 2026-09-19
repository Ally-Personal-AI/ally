"""Human-facing personal knowledge commands."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from ally.commands._storage import build_knowledge_store
from ally.knowledge.ingestion import TextKnowledgeIngestor
from ally.knowledge.retrieval import LexicalKnowledgeRetriever


def _parse_source_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid knowledge source ID: {value}") from exc


def run_ingest_knowledge_file(*, path: str) -> int:
    store = build_knowledge_store()
    ingestor = TextKnowledgeIngestor(store)

    try:
        source, revision = ingestor.ingest_file(Path(path))
    except ValueError as exc:
        print(f"Knowledge ingest error: {exc}")
        return 2

    print(f"Source: {source.id}")
    print(f"Revision: {revision.revision}")
    print(f"SHA-256: {revision.sha256}")
    return 0


def run_list_knowledge_sources(*, limit: int) -> int:
    try:
        sources = build_knowledge_store().list_sources(limit=limit)
    except ValueError as exc:
        print(f"Knowledge error: {exc}")
        return 2

    if not sources:
        print("No knowledge sources.")
        return 0

    for source in sources:
        print(
            f"{source.id}  r{source.current_revision}  "
            f"{source.media_type}  {source.title}"
        )
    return 0


def run_show_knowledge_source(*, source_id: str) -> int:
    try:
        identifier = _parse_source_id(source_id)
    except ValueError as exc:
        print(exc)
        return 2

    store = build_knowledge_store()
    source = store.get_source(identifier)
    if source is None:
        print(f"Knowledge source not found: {identifier}")
        return 2

    revisions = store.list_revisions(identifier)
    current_chunks = store.list_current_chunks(identifier)

    print(f"Source: {source.id}")
    print(f"Title: {source.title}")
    print(f"URI: {source.uri}")
    print(f"Media type: {source.media_type}")
    print(f"Current revision: {source.current_revision}")
    print(f"Current chunks: {len(current_chunks)}")
    print("Revisions:")
    for revision in revisions:
        print(
            f"  r{revision.revision}  {revision.created_at.isoformat()}  "
            f"{revision.sha256}"
        )
    return 0


def run_search_knowledge(*, query: str, limit: int) -> int:
    store = build_knowledge_store()
    try:
        hits = LexicalKnowledgeRetriever(store, limit=limit).retrieve(query)
    except ValueError as exc:
        print(f"Knowledge error: {exc}")
        return 2

    if not hits:
        print("No matching knowledge.")
        return 0

    for hit in hits:
        print(
            f"{hit.source.id}  r{hit.chunk.revision}:c{hit.chunk.ordinal}  "
            f"{hit.source.title}"
        )
        print(hit.chunk.content)
        print()
    return 0
