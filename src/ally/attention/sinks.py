"""Attention delivery sink contracts and development sink."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Protocol

from ally.events import AttentionClass, EventRecord

DELIVERABLE_ATTENTION_CLASSES: tuple[AttentionClass, ...] = (
    "mention_later",
    "notify",
    "interrupt",
)


class AttentionSink(Protocol):
    @property
    def id(self) -> str:
        ...

    @property
    def accepted_attention(self) -> tuple[AttentionClass, ...]:
        ...

    def deliver(
        self,
        event: EventRecord,
        *,
        delivery_key: str,
    ) -> None:
        ...


class ConsoleAttentionSink:
    """Development sink that renders attention without OS integration."""

    def __init__(self, writer: Callable[[str], None] = print) -> None:
        self._writer = writer

    @property
    def id(self) -> str:
        return "console"

    @property
    def accepted_attention(self) -> tuple[AttentionClass, ...]:
        return DELIVERABLE_ATTENTION_CLASSES

    def deliver(
        self,
        event: EventRecord,
        *,
        delivery_key: str,
    ) -> None:
        rendered = json.dumps(event.payload, sort_keys=True)
        self._writer(
            f"[{event.attention}] {event.type} source={event.source} "
            f"delivery={delivery_key} payload={rendered}"
        )
