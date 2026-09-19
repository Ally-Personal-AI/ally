"""Registration and lookup for tools."""

from __future__ import annotations

from ally.tools.tool import Tool


class ToolRegistry:
    """Explicit registry for tools available to an Ally runtime."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        name = tool.spec.name
        if name in self._tools:
            raise ValueError(f"Tool already registered: {name}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> tuple[Tool, ...]:
        return tuple(self._tools[name] for name in sorted(self._tools))
