"""Human-facing memory presentation adapter."""

from __future__ import annotations

from uuid import UUID

from ally.application import (
    ApplicationNotFoundError,
    RememberMemoryRequest,
    SupersedeMemoryRequest,
)
from ally.composition import build_default_application
from ally.memory import MemoryKind, MemoryPrivacy


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
    try:
        record = build_default_application().remember(
            RememberMemoryRequest(
                content=content,
                kind=kind,
                confidence=confidence,
                importance=importance,
                privacy=privacy,
            )
        )
    except ValueError as exc:
        print(f"Memory error: {exc}")
        return 2
    print(record.id)
    return 0


def run_list_memories(
    *,
    kind: MemoryKind | None,
    include_inactive: bool,
    limit: int,
) -> int:
    try:
        records = build_default_application().list_memories(
            kind=kind,
            include_inactive=include_inactive,
            limit=limit,
        )
    except ValueError as exc:
        print(f"Memory error: {exc}")
        return 2

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
    try:
        records = build_default_application().search_memories(query, limit=limit)
    except ValueError as exc:
        print(f"Memory error: {exc}")
        return 2

    if not records:
        print("No matching memories.")
        return 0
    for record in records:
        print(f"{record.id}  {record.kind}  {record.content}")
    return 0


def run_show_memory(*, memory_id: str) -> int:
    try:
        record = build_default_application().memory(_parse_id(memory_id))
    except (ApplicationNotFoundError, ValueError) as exc:
        print(exc)
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
        replacement = build_default_application().supersede_memory(
            SupersedeMemoryRequest(
                memory_id=_parse_id(memory_id),
                content=content,
            )
        )
    except ApplicationNotFoundError as exc:
        print(exc)
        return 2
    except ValueError as exc:
        print(f"Memory cannot be superseded: {exc}")
        return 2

    print(replacement.id)
    return 0


def run_retract_memory(*, memory_id: str) -> int:
    try:
        record = build_default_application().retract_memory(_parse_id(memory_id))
    except (ApplicationNotFoundError, ValueError) as exc:
        print(exc)
        return 2

    print(record.id)
    return 0
