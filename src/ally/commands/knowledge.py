"""Human-facing personal-knowledge presentation adapter."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from ally.application import ApplicationNotFoundError
from ally.composition import build_default_application


def _parse_source_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid knowledge source ID: {value}") from exc


def run_ingest_knowledge_file(*, path: str) -> int:
    try:
        result = build_default_application().ingest_knowledge_file(Path(path))
    except ValueError as exc:
        print(f"Knowledge ingest error: {exc}")
        return 2

    print(f"Source: {result.source.id}")
    print(f"Revision: {result.revision.revision}")
    print(f"SHA-256: {result.revision.sha256}")
    return 0


def run_list_knowledge_sources(*, limit: int) -> int:
    try:
        sources = build_default_application().list_knowledge_sources(limit=limit)
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
        view = build_default_application().knowledge_source(
            _parse_source_id(source_id)
        )
    except (ApplicationNotFoundError, ValueError) as exc:
        print(exc)
        return 2

    source = view.source
    print(f"Source: {source.id}")
    print(f"Title: {source.title}")
    print(f"URI: {source.uri}")
    print(f"Media type: {source.media_type}")
    print(f"Current revision: {source.current_revision}")
    print(f"Current chunks: {len(view.current_chunks)}")
    print("Revisions:")
    for revision in view.revisions:
        print(
            f"  r{revision.revision}  {revision.created_at.isoformat()}  "
            f"{revision.sha256}"
        )
    return 0


def run_search_knowledge(*, query: str, limit: int) -> int:
    try:
        hits = build_default_application().search_knowledge(query, limit=limit)
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
