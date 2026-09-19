"""Tool implementation contract."""

from __future__ import annotations

from typing import Protocol

from pydantic import JsonValue

from ally.tools.models import ToolSpec


class Tool(Protocol):
    """A capability callable through Ally's policy-enforced tool runtime."""

    @property
    def spec(self) -> ToolSpec:
        ...

    def run(self, arguments: dict[str, JsonValue]) -> JsonValue:
        ...
