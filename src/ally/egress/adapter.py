"""External-service adapter contract for controlled egress."""

from __future__ import annotations

from typing import Protocol

from pydantic import JsonValue


class EgressAdapter(Protocol):
    """A concrete external service reachable only after egress policy."""

    @property
    def service(self) -> str:
        ...

    def send(
        self,
        operation: str,
        payload: dict[str, JsonValue],
    ) -> JsonValue:
        ...
