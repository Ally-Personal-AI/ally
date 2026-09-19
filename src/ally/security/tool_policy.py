"""Deterministic authorization policy for tool execution."""

from __future__ import annotations

from typing import Literal

from ally.tools.models import ToolSpec

PolicyDecision = Literal["allow", "require_approval", "deny"]


class DefaultToolPolicy:
    """Conservative default policy independent of model instructions."""

    def decide(self, spec: ToolSpec, *, approved: bool) -> PolicyDecision:
        if spec.risk == "read_only":
            return "allow"
        if spec.risk in {"reversible", "external_consequence"}:
            return "allow" if approved else "require_approval"
        return "deny"
