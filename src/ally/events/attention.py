"""Deterministic default attention policy."""

from __future__ import annotations

from ally.events.models import AttentionClass, EventImportance, NewEvent


class DefaultAttentionPolicy:
    """Map explicit event importance to a conservative attention class."""

    def classify(self, event: NewEvent) -> AttentionClass:
        mapping: dict[EventImportance, AttentionClass] = {
            "noise": "ignore",
            "routine": "remember",
            "important": "mention_later",
            "urgent": "notify",
            "critical": "interrupt",
        }
        return mapping[event.importance]
