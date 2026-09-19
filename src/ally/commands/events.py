"""Human-facing proactive event commands."""

from __future__ import annotations

import json
from typing import cast
from uuid import UUID

from pydantic import JsonValue

from ally.commands._storage import build_event_store
from ally.events import AttentionClass, EventImportance, EventRuntime, NewEvent


def run_emit_event(
    *,
    event_type: str,
    source: str,
    importance: EventImportance,
    payload_json: str,
) -> int:
    try:
        raw = json.loads(payload_json)
    except json.JSONDecodeError as exc:
        print(f"Event payload must be valid JSON: {exc}")
        return 2

    if not isinstance(raw, dict):
        print("Event payload must be a JSON object.")
        return 2

    event = NewEvent(
        type=event_type,
        source=source,
        importance=importance,
        payload=cast(dict[str, JsonValue], raw),
    )
    record = EventRuntime(build_event_store()).publish(event)

    print(f"Event: {record.id}")
    print(f"Attention: {record.attention}")
    return 0


def run_list_events(
    *,
    limit: int,
    attention: AttentionClass | None,
    handled: bool | None,
) -> int:
    try:
        records = build_event_store().list(
            limit=limit,
            attention=attention,
            handled=handled,
        )
    except ValueError as exc:
        print(f"Event error: {exc}")
        return 2

    if not records:
        print("No events.")
        return 0

    for record in records:
        status = "handled" if record.handled_at is not None else "pending"
        print(
            f"{record.id}  {record.attention}  {status}  "
            f"{record.type}  {record.source}"
        )
    return 0


def run_show_event(*, event_id: str) -> int:
    try:
        identifier = UUID(event_id)
    except ValueError:
        print(f"Invalid event ID: {event_id}")
        return 2

    record = build_event_store().get(identifier)
    if record is None:
        print(f"Event not found: {identifier}")
        return 2

    print(f"Event: {record.id}")
    print(f"Type: {record.type}")
    print(f"Source: {record.source}")
    print(f"Importance: {record.importance}")
    print(f"Attention: {record.attention}")
    print(f"Created: {record.created_at.isoformat()}")
    handled = record.handled_at.isoformat() if record.handled_at else "(pending)"
    print(f"Handled: {handled}")
    print(json.dumps(record.payload, indent=2, sort_keys=True))
    return 0


def run_handle_event(*, event_id: str) -> int:
    try:
        identifier = UUID(event_id)
    except ValueError:
        print(f"Invalid event ID: {event_id}")
        return 2

    try:
        record = build_event_store().mark_handled(identifier)
    except KeyError as exc:
        print(f"Event error: {exc}")
        return 2

    print(record.id)
    return 0
