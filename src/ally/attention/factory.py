"""Composition helpers for explicit attention sinks."""

from __future__ import annotations

import sys
from typing import Literal

from ally.attention.macos import (
    MacOSNotificationError,
    MacOSNotificationSink,
    MacOSNotificationStatus,
)
from ally.attention.sinks import AttentionSink, ConsoleAttentionSink

AttentionSinkName = Literal["auto", "console", "macos"]


def build_attention_sink(name: AttentionSinkName) -> AttentionSink:
    """Build one explicit sink without changing durable delivery semantics."""

    selected = "macos" if name == "auto" and sys.platform == "darwin" else name
    if selected == "auto":
        selected = "console"
    if selected == "console":
        return ConsoleAttentionSink()
    if selected == "macos":
        return MacOSNotificationSink()
    raise ValueError(f"unknown attention sink: {name}")


def macos_notification_status() -> MacOSNotificationStatus:
    """Return payload-free native sink readiness or a safe unavailable status."""

    try:
        return MacOSNotificationSink().status()
    except MacOSNotificationError:
        return MacOSNotificationStatus(
            supported=sys.platform == "darwin",
            api_available=False,
            authorization="unobservable",
        )
