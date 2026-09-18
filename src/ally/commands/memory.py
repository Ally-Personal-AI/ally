"""Human-facing memory inspection and correction commands."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from ally.commands._storage import build_memory_store
from ally.memory import (
    MemoryKind,
    MemoryPrivacy,
    MemorySource,
    NewMemory,
)


def _parse_id(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid memory ID: {value}") from exc


def run_remember(
    *,
    content: str,
    kind: MemoryKind,
    confidence: float,
    importance: float,
    privacy: MemoryPrivacy,
) -> int:
    store = build_memory_store()
    record = store.create(
        NewMemory(
            kind=kind,
            content=content,
            source=MemorySource(type="user"),
            confidence=confidence,
            importance=importance,
            privacy=privacy,
            observed_at=datetime.now(UTC),
        )
    )
    print(record.id)
    return 0


def run_list_memories(
    *,
    kind: MemoryKind | None,
    include_inactive: bool,
    limit: int,
) -> int:
    store = build_memory_store()
    records = store.list(
        kind=kind,
        include_inactive=include_inactive,
        limit=limit,
    )
    if not records:
        print("No memories.")
        return 0

    for record in records:
        state = "active"
        if record.superseded_at is not None:
            state = "superseded"
        elif record.retracted_at is not None:
            state = "retracted"
        print(f"{record.id}  {record.kind}  {state}  {record.content}")
    return 0


def run_search_memories(*, query: str, limit: int) -> int:
    records = build_memory_store().search(query, limit=limit)
    if not records:
        print("No matching memories.")
        return 0
    for record in records:
        print(f"{record.id}  {record.kind}  {record.content}")
    return 0


def run_show_memory(*, memory_id: str) -> int:
    try:
        identifier = _parse_id(memory_id)
    except ValueError as exc:
        print(exc)
        return 2

    record = build_memory_store().get(identifier)
    if record is None:
        print(f"Memory not found: {identifier}")
        return 2

    print(f"Memory: {record.id}")
    print(f"Kind: {record.kind}")
    print(f"Content: {record.content}")
    print(f"Source: {record.source.type}")
    print(f"Confidence: {record.confidence}")
    print(f"Importance: {record.importance}")
    print(f"Privacy: {record.privacy}")
    print(f"Created: {record.created_at.isoformat()}")
    if record.valid_from is not None:
        print(f"Valid from: {record.valid_from.isoformat()}")
    if record.valid_until is not None:
        print(f"Valid until: {record.valid_until.isoformat()}")
    if record.superseded_by is not None:
        print(f"Superseded by: {record.superseded_by}")
    if record.retracted_at is not None:
        print(f"Retracted: {record.retracted_at.isoformat()}")
    return 0


def run_supersede_memory(*, memory_id: str, content: str) -> int:
    try:
        identifier = _parse_id(memory_id)
    except ValueError as exc:
        print(exc)
        return 2

    store = build_memory_store()
    existing = store.get(identifier)
    if existing is None:
        print(f"Memory not found: {identifier}")
        return 2

    try:
        _, replacement = store.supersede(
            existing.id,
            NewMemory(
                kind=existing.kind,
                content=content,
                source=MemorySource(type="user"),
                confidence=1.0,
                importance=existing.importance,
                privacy=existing.privacy,
                observed_at=datetime.now(UTC),
                valid_from=existing.valid_from,
                valid_until=existing.valid_until,
            ),
        )
    except ValueError as exc:
        print(f"Memory cannot be superseded: {exc}")
        return 2

    print(replacement.id)
    return 0


def run_retract_memory(*, memory_id: str) -> int:
    try:
        identifier = _parse_id(memory_id)
    except ValueError as exc:
        print(exc)
        return 2

    try:
        record = build_memory_store().retract(identifier)
    except KeyError:
        print(f"Memory not found: {identifier}")
        return 2

    print(record.id)
    return 0
