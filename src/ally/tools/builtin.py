"""Small built-in tools that are safe to expose by default."""

from __future__ import annotations

import platform
import sys

from pydantic import JsonValue

from ally.tools.models import ToolSpec


class SystemInfoTool:
    """Read-only runtime information useful for diagnostics."""

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(
            name="system.info",
            description="Return local Python and operating-system runtime information.",
            risk="read_only",
        )

    def run(self, arguments: dict[str, JsonValue]) -> JsonValue:
        if arguments:
            raise ValueError("system.info accepts no arguments")
        return {
            "python_version": platform.python_version(),
            "python_implementation": platform.python_implementation(),
            "platform": sys.platform,
            "machine": platform.machine(),
        }


def build_default_tool_registry():
    from ally.tools.registry import ToolRegistry

    registry = ToolRegistry()
    registry.register(SystemInfoTool())
    return registry
