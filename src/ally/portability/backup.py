"""Versioned, integrity-checked Ally database archives."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ally import __version__
from ally.storage.errors import DatabaseMigrationError
from ally.storage.sqlite.database import SQLiteDatabase, read_schema_versions

_MANIFEST_NAME = "manifest.json"
_DATABASE_NAME = "ally.sqlite3"
_ARCHIVE_MEMBERS = {_MANIFEST_NAME, _DATABASE_NAME}


class BackupValidationError(ValueError):
    """Raised when an Ally backup archive fails validation."""


class BackupDatabaseEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    filename: Literal["ally.sqlite3"] = _DATABASE_NAME
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    schema_versions: tuple[int, ...]


class BackupManifest(BaseModel):
    """Manifest for Ally backup archive format V1."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    format: Literal["ally-backup"] = "ally-backup"
    schema_version: Literal[1] = 1
    created_at: datetime
    ally_version: str
    database: BackupDatabaseEntry


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _schema_versions(path: Path) -> tuple[int, ...]:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return read_schema_versions(connection)
    except (sqlite3.DatabaseError, DatabaseMigrationError) as exc:
        raise BackupValidationError(
            "database is missing valid or supported Ally schema metadata"
        ) from exc
    finally:
        connection.close()


def _check_sqlite_integrity(path: Path) -> None:
    connection = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
        foreign_key_error = connection.execute("PRAGMA foreign_key_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise BackupValidationError("SQLite integrity check failed") from exc
    finally:
        connection.close()

    if row is None or row[0] != "ok":
        raise BackupValidationError("SQLite integrity check did not pass")
    if foreign_key_error is not None:
        raise BackupValidationError("SQLite foreign-key integrity check did not pass")


def _new_destination(path: Path, kind: str) -> Path:
    expanded = path.expanduser()
    # Resolve the parent only: even a dangling destination symlink is occupied.
    resolved = expanded.parent.resolve() / expanded.name
    if resolved.exists() or resolved.is_symlink():
        raise FileExistsError(f"refusing to overwrite existing {kind}: {resolved}")
    if kind == "database":
        for suffix in ("-wal", "-shm", "-journal"):
            sidecar = resolved.with_name(resolved.name + suffix)
            if sidecar.exists() or sidecar.is_symlink():
                raise FileExistsError("refusing database destination with existing SQLite sidecars")
    return resolved


def _publish_new_file(staged: Path, destination: Path, kind: str) -> None:
    """Atomically create a destination name without replacing another writer's file."""

    try:
        # Both paths have the same parent/filesystem. Unsupported hard links fail
        # closed; copying or replacing would weaken the no-overwrite guarantee.
        os.link(staged, destination)
    except FileExistsError as exc:
        raise FileExistsError(
            f"refusing to overwrite existing {kind}: {destination}"
        ) from exc


def _snapshot_database(database: SQLiteDatabase, destination: Path) -> None:
    database.migrate()
    destination.parent.mkdir(parents=True, exist_ok=True)

    with database.connect() as source:
        target = sqlite3.connect(destination)
        try:
            source.backup(target)
            target.commit()
        finally:
            target.close()

    _check_sqlite_integrity(destination)


def create_backup(
    database: SQLiteDatabase,
    destination: Path,
) -> BackupManifest:
    """Create an atomic versioned archive containing only Ally database state."""

    source_path = database.path.expanduser().resolve()
    if destination.expanduser().resolve() == source_path:
        raise ValueError("backup destination cannot be the live database path")
    resolved = _new_destination(destination, "backup")

    resolved.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ally-backup-") as temporary:
        temp_dir = Path(temporary)
        snapshot = temp_dir / _DATABASE_NAME
        _snapshot_database(database, snapshot)

        manifest = BackupManifest(
            created_at=datetime.now(UTC),
            ally_version=__version__,
            database=BackupDatabaseEntry(
                sha256=_sha256(snapshot),
                size_bytes=snapshot.stat().st_size,
                schema_versions=_schema_versions(snapshot),
            ),
        )
        manifest_path = temp_dir / _MANIFEST_NAME
        manifest_path.write_text(
            json.dumps(
                manifest.model_dump(mode="json"),
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        temporary_archive = resolved.with_name(
            f".{resolved.name}.{uuid4().hex}.tmp"
        )
        try:
            with ZipFile(
                temporary_archive,
                mode="w",
                compression=ZIP_DEFLATED,
            ) as archive:
                archive.write(manifest_path, arcname=_MANIFEST_NAME)
                archive.write(snapshot, arcname=_DATABASE_NAME)
            _publish_new_file(temporary_archive, resolved, "backup")
        finally:
            temporary_archive.unlink(missing_ok=True)

    return manifest


def _read_archive(
    archive_path: Path,
    temporary_dir: Path,
) -> tuple[BackupManifest, Path]:
    try:
        with ZipFile(archive_path, mode="r") as archive:
            names = archive.namelist()
            if len(names) != len(_ARCHIVE_MEMBERS) or set(names) != _ARCHIVE_MEMBERS:
                raise BackupValidationError(
                    "backup V1 must contain exactly manifest.json and ally.sqlite3"
                )

            try:
                manifest = BackupManifest.model_validate_json(
                    archive.read(_MANIFEST_NAME)
                )
            except (KeyError, ValidationError) as exc:
                raise BackupValidationError("invalid backup manifest") from exc

            database_bytes = archive.read(_DATABASE_NAME)
    except (BadZipFile, OSError) as exc:
        raise BackupValidationError("invalid backup archive") from exc

    snapshot = temporary_dir / _DATABASE_NAME
    snapshot.write_bytes(database_bytes)

    if snapshot.stat().st_size != manifest.database.size_bytes:
        raise BackupValidationError("database size does not match manifest")
    if _sha256(snapshot) != manifest.database.sha256:
        raise BackupValidationError("database SHA-256 does not match manifest")

    _check_sqlite_integrity(snapshot)
    actual_versions = _schema_versions(snapshot)
    if actual_versions != manifest.database.schema_versions:
        raise BackupValidationError(
            "database schema versions do not match manifest"
        )

    return manifest, snapshot


def validate_backup(path: Path) -> BackupManifest:
    """Validate archive structure, hashes, schema metadata, and SQLite integrity."""

    resolved = path.expanduser().resolve()
    with tempfile.TemporaryDirectory(prefix="ally-validate-") as temporary:
        manifest, _ = _read_archive(resolved, Path(temporary))
        return manifest


def restore_backup(
    archive_path: Path,
    destination: Path,
) -> BackupManifest:
    """Restore an archive into a database path that does not already exist."""

    resolved_archive = archive_path.expanduser().resolve()
    resolved_destination = _new_destination(destination, "database")

    resolved_destination.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ally-restore-") as temporary:
        manifest, snapshot = _read_archive(
            resolved_archive,
            Path(temporary),
        )
        staged = resolved_destination.with_name(
            f".{resolved_destination.name}.{uuid4().hex}.restore"
        )

        try:
            staged.write_bytes(snapshot.read_bytes())
            database = SQLiteDatabase(staged)
            try:
                database.migrate()
            except DatabaseMigrationError as exc:
                raise BackupValidationError(
                    "backup database could not be upgraded; destination was not created"
                ) from exc
            _check_sqlite_integrity(staged)
            _publish_new_file(staged, resolved_destination, "database")
        finally:
            staged.unlink(missing_ok=True)

    return manifest
