"""Deterministic local JSONL reference event source."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from ally.sources.models import EventSourceObservation, EventSourcePollResult
from ally.sources.runtime import validate_source_id


class JsonlEventSource:
    """Read validated observations from an explicit local JSONL file."""

    def __init__(
        self,
        *,
        source_id: str,
        path: Path,
    ) -> None:
        self._id = validate_source_id(source_id)
        self._path = path.expanduser().resolve()

    @property
    def id(self) -> str:
        return self._id

    def poll(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> EventSourcePollResult:
        if limit < 1:
            raise ValueError("limit must be positive")

        start = self._parse_cursor(cursor)
        observations: list[EventSourceObservation] = []
        consumed = start

        try:
            handle = self._path.open("r", encoding="utf-8")
        except OSError as exc:
            raise ValueError(f"could not read JSONL source: {self._path}") from exc

        with handle:
            for index, line in enumerate(handle):
                if index < start:
                    continue
                if len(observations) >= limit:
                    break

                rendered = line.strip()
                if not rendered:
                    raise ValueError(
                        f"JSONL source contains blank line at {index + 1}"
                    )

                try:
                    raw = json.loads(rendered)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"invalid JSONL observation at line {index + 1}"
                    ) from exc

                try:
                    observation = EventSourceObservation.model_validate(raw)
                except ValidationError as exc:
                    raise ValueError(
                        f"invalid event observation at line {index + 1}: {exc}"
                    ) from exc

                observations.append(observation)
                consumed = index + 1

        if consumed == start and start > 0:
            total_lines = self._line_count()
            if start > total_lines:
                raise ValueError(
                    "JSONL source cursor is beyond the current file length"
                )

        return EventSourcePollResult(
            observations=tuple(observations),
            next_cursor=str(consumed),
        )

    def _line_count(self) -> int:
        try:
            with self._path.open("r", encoding="utf-8") as handle:
                return sum(1 for _ in handle)
        except OSError as exc:
            raise ValueError(f"could not read JSONL source: {self._path}") from exc

    @staticmethod
    def _parse_cursor(cursor: str | None) -> int:
        if cursor is None:
            return 0
        try:
            value = int(cursor)
        except ValueError as exc:
            raise ValueError(f"invalid JSONL cursor: {cursor}") from exc
        if value < 0:
            raise ValueError("JSONL cursor cannot be negative")
        return value
