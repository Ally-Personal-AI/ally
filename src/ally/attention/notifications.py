"""Payload-minimized rendering shared by local notification adapters."""

from __future__ import annotations

from ally.events import EventRecord

_MAX_NOTIFICATION_TEXT = 500


def _bounded_text(value: str) -> str:
    compact = " ".join(value.split()).strip()
    if len(compact) <= _MAX_NOTIFICATION_TEXT:
        return compact
    return compact[: _MAX_NOTIFICATION_TEXT - 1].rstrip() + "…"


def render_notification(event: EventRecord) -> tuple[str, str]:
    """Render explicit user-facing text without dumping arbitrary event payloads."""

    title = "Ally"
    if event.attention == "interrupt":
        title = "Ally — Important"

    body: str | None = None
    for key in ("summary", "message"):
        value = event.payload.get(key)
        if isinstance(value, str) and value.strip():
            body = value
            break

    return title, _bounded_text(body or event.type)
