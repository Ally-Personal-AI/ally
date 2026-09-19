"""Bounded metadata-only polling for an explicitly allowlisted directory."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal, cast

from pydantic import JsonValue

from ally.events import EventImportance
from ally.sources.models import EventSourceObservation, EventSourcePollResult
from ally.sources.runtime import validate_source_id

_CURSOR_VERSION = 1
_MAX_CURSOR_LENGTH = 1_048_576
_MAX_RELATIVE_PATH_LENGTH = 1024


@dataclass(frozen=True)
class _Entry:
    path: str
    device: int
    inode: int
    size: int
    modified_ns: int

    @property
    def identity(self) -> tuple[int, int]:
        return (self.device, self.inode)

    @property
    def revision(self) -> tuple[int, int]:
        return (self.size, self.modified_ns)

    def cursor_data(self) -> dict[str, int | str]:
        return {
            "path": self.path,
            "device": self.device,
            "inode": self.inode,
            "size": self.size,
            "modified_ns": self.modified_ns,
        }


@dataclass(frozen=True)
class _Cursor:
    sequence: int
    entries: dict[str, _Entry]


_ChangeKind = Literal["created", "modified", "moved", "deleted"]


@dataclass(frozen=True)
class _Change:
    kind: _ChangeKind
    before: _Entry | None = None
    after: _Entry | None = None

    @property
    def path(self) -> str:
        entry = self.after or self.before
        assert entry is not None
        return entry.path


class FilesystemEventSource:
    """Observe regular-file metadata below one explicit directory.

    The source never reads file contents and never follows symbolic links. Its
    opaque cursor contains a relative-path metadata snapshot and a monotonic
    sequence used to make event identities replay-stable.
    """

    def __init__(
        self,
        *,
        source_id: str,
        root: Path,
        max_entries: int = 1000,
        include_hidden: bool = False,
        importance: EventImportance = "routine",
    ) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")

        candidate = root.expanduser()
        if candidate.is_symlink():
            raise ValueError("filesystem source root cannot be a symbolic link")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise ValueError(f"filesystem source root is unavailable: {candidate}") from exc
        if not resolved.is_dir():
            raise ValueError(f"filesystem source root is not a directory: {resolved}")

        self._id = validate_source_id(source_id)
        self._root = resolved
        self._max_entries = max_entries
        self._include_hidden = include_hidden
        self._importance: EventImportance = importance

    @property
    def id(self) -> str:
        return self._id

    @property
    def root(self) -> Path:
        return self._root

    def poll(
        self,
        *,
        cursor: str | None,
        limit: int,
    ) -> EventSourcePollResult:
        if limit < 1:
            raise ValueError("limit must be positive")

        previous = self._decode_cursor(cursor)
        current = self._scan()
        if previous is None:
            return EventSourcePollResult(
                observations=(),
                next_cursor=self._encode_cursor(_Cursor(sequence=0, entries=current)),
            )

        changes = self._changes(previous.entries, current)
        selected = changes[:limit]
        next_entries = dict(previous.entries)
        observations: list[EventSourceObservation] = []

        for offset, change in enumerate(selected, start=1):
            sequence = previous.sequence + offset
            observations.append(
                self._observation(
                    change,
                    sequence=sequence,
                    importance=self._importance,
                )
            )
            self._apply(next_entries, change)

        next_cursor = self._encode_cursor(
            _Cursor(
                sequence=previous.sequence + len(selected),
                entries=next_entries,
            )
        )
        return EventSourcePollResult(
            observations=tuple(observations),
            next_cursor=next_cursor,
        )

    def _scan(self) -> dict[str, _Entry]:
        entries: dict[str, _Entry] = {}
        directories = [self._root]
        inspected = 0

        while directories:
            directory = directories.pop()
            try:
                with os.scandir(directory) as handle:
                    children = sorted(handle, key=lambda item: item.name, reverse=True)
            except OSError as exc:
                raise ValueError(
                    f"filesystem source could not scan directory: {directory}"
                ) from exc

            for child in children:
                inspected += 1
                if inspected > self._max_entries:
                    raise ValueError("filesystem source exceeded configured max_entries")
                if not self._include_hidden and child.name.startswith("."):
                    continue

                path = Path(child.path)
                try:
                    if child.is_symlink():
                        continue
                    if child.is_dir(follow_symlinks=False):
                        directories.append(path)
                        continue
                    if not child.is_file(follow_symlinks=False):
                        continue
                    stat = child.stat(follow_symlinks=False)
                except OSError as exc:
                    raise ValueError(f"filesystem source could not inspect entry: {path}") from exc

                try:
                    relative = path.relative_to(self._root).as_posix()
                except ValueError as exc:
                    raise ValueError("filesystem source entry escaped configured root") from exc
                self._validate_relative_path(relative)
                entries[relative] = _Entry(
                    path=relative,
                    device=stat.st_dev,
                    inode=stat.st_ino,
                    size=stat.st_size,
                    modified_ns=stat.st_mtime_ns,
                )

        return entries

    @classmethod
    def _decode_cursor(cls, value: str | None) -> _Cursor | None:
        if value is None:
            return None
        if len(value) > _MAX_CURSOR_LENGTH:
            raise ValueError("filesystem source cursor is too large")
        try:
            raw_value: object = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid filesystem source cursor") from exc
        if not isinstance(raw_value, dict):
            raise ValueError("invalid filesystem source cursor")
        raw = cast(dict[str, object], raw_value)
        if set(raw) != {"version", "sequence", "entries"}:
            raise ValueError("invalid filesystem source cursor")
        if raw["version"] != _CURSOR_VERSION:
            raise ValueError("unsupported filesystem source cursor version")
        sequence_value = raw["sequence"]
        raw_entries_value = raw["entries"]
        if not cls._is_nonnegative_int(sequence_value) or not isinstance(raw_entries_value, list):
            raise ValueError("invalid filesystem source cursor")
        sequence = cast(int, sequence_value)
        raw_entries = cast(list[object], raw_entries_value)

        entries: dict[str, _Entry] = {}
        for raw_entry_value in raw_entries:
            if not isinstance(raw_entry_value, dict):
                raise ValueError("invalid filesystem source cursor entry")
            raw_entry = cast(dict[str, object], raw_entry_value)
            if set(raw_entry) != {
                "path",
                "device",
                "inode",
                "size",
                "modified_ns",
            }:
                raise ValueError("invalid filesystem source cursor entry")
            path = raw_entry["path"]
            if not isinstance(path, str):
                raise ValueError("invalid filesystem source cursor entry")
            cls._validate_relative_path(path)
            numeric = (
                raw_entry["device"],
                raw_entry["inode"],
                raw_entry["size"],
                raw_entry["modified_ns"],
            )
            if not all(cls._is_nonnegative_int(item) for item in numeric):
                raise ValueError("invalid filesystem source cursor entry")
            if path in entries:
                raise ValueError("filesystem source cursor contains duplicate paths")
            entries[path] = _Entry(
                path=path,
                device=cast(int, raw_entry["device"]),
                inode=cast(int, raw_entry["inode"]),
                size=cast(int, raw_entry["size"]),
                modified_ns=cast(int, raw_entry["modified_ns"]),
            )

        return _Cursor(sequence=sequence, entries=entries)

    @staticmethod
    def _encode_cursor(cursor: _Cursor) -> str:
        rendered = json.dumps(
            {
                "version": _CURSOR_VERSION,
                "sequence": cursor.sequence,
                "entries": [cursor.entries[path].cursor_data() for path in sorted(cursor.entries)],
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(rendered) > _MAX_CURSOR_LENGTH:
            raise ValueError("filesystem source cursor exceeds safe storage limit")
        return rendered

    @classmethod
    def _changes(
        cls,
        previous: dict[str, _Entry],
        current: dict[str, _Entry],
    ) -> tuple[_Change, ...]:
        removed = set(previous) - set(current)
        added = set(current) - set(previous)

        previous_identities = cls._unique_identities(previous, removed)
        current_identities = cls._unique_identities(current, added)
        moved: list[_Change] = []
        for identity in sorted(previous_identities.keys() & current_identities.keys()):
            before_path = previous_identities[identity]
            after_path = current_identities[identity]
            removed.remove(before_path)
            added.remove(after_path)
            moved.append(
                _Change(
                    kind="moved",
                    before=previous[before_path],
                    after=current[after_path],
                )
            )

        changes = moved
        changes.extend(_Change(kind="deleted", before=previous[path]) for path in removed)
        changes.extend(_Change(kind="created", after=current[path]) for path in added)
        changes.extend(
            _Change(kind="modified", before=previous[path], after=current[path])
            for path in previous.keys() & current.keys()
            if previous[path].revision != current[path].revision
        )
        return tuple(
            sorted(
                changes,
                key=lambda change: (
                    change.path,
                    change.kind,
                    "" if change.before is None else change.before.path,
                ),
            )
        )

    @staticmethod
    def _unique_identities(
        entries: dict[str, _Entry],
        paths: set[str],
    ) -> dict[tuple[int, int], str]:
        candidates: dict[tuple[int, int], list[str]] = {}
        for path in paths:
            candidates.setdefault(entries[path].identity, []).append(path)
        return {
            identity: matches[0] for identity, matches in candidates.items() if len(matches) == 1
        }

    @staticmethod
    def _apply(entries: dict[str, _Entry], change: _Change) -> None:
        if change.before is not None:
            entries.pop(change.before.path, None)
        if change.after is not None:
            entries[change.after.path] = change.after

    @staticmethod
    def _observation(
        change: _Change,
        *,
        sequence: int,
        importance: EventImportance,
    ) -> EventSourceObservation:
        identity_data: dict[str, object] = {
            "kind": change.kind,
            "before": None if change.before is None else change.before.cursor_data(),
            "after": None if change.after is None else change.after.cursor_data(),
        }
        digest = hashlib.sha256(
            json.dumps(
                identity_data,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()

        payload: dict[str, JsonValue] = {
            "change": change.kind,
            "path": change.path,
            "entry_type": "file",
        }
        if change.before is not None and change.kind == "moved":
            payload["previous_path"] = change.before.path
        if change.before is not None:
            payload["previous_size"] = change.before.size
            payload["previous_modified_ns"] = change.before.modified_ns
        if change.after is not None:
            payload["size"] = change.after.size
            payload["modified_ns"] = change.after.modified_ns

        return EventSourceObservation(
            external_id=f"fs:{sequence}:{digest}",
            event_type=f"filesystem.{change.kind}",
            importance=importance,
            payload=payload,
        )

    @staticmethod
    def _validate_relative_path(value: str) -> None:
        path = PurePosixPath(value)
        if (
            not value
            or len(value) > _MAX_RELATIVE_PATH_LENGTH
            or path.is_absolute()
            or value != path.as_posix()
            or any(part in {"", ".", ".."} for part in path.parts)
        ):
            raise ValueError("invalid relative path in filesystem source cursor")

    @staticmethod
    def _is_nonnegative_int(value: object) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) and value >= 0
