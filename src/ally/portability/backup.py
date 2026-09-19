"""Versioned, integrity-checked Ally database archives."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ally import __version__
from ally.storage.sqlite.database import SQLiteDatabase
from ally.storage.sqlite.schema import MIGRATIONS

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
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT version FROM ally_schema_migrations ORDER BY version"
        ).fetchall()
    except sqlite3.DatabaseError as exc:
        raise BackupValidationError(
            "database is missing valid Ally schema metadata"
        ) from exc
    finally:
        connection.close()

    return tuple(cast(int, row[0]) for row in rows)


def _check_sqlite_integrity(path: Path) -> None:
    connection = sqlite3.connect(path)
    try:
        row = connection.execute("PRAGMA integrity_check").fetchone()
    except sqlite3.DatabaseError as exc:
        raise BackupValidationError("SQLite integrity check failed") from exc
    finally:
        connection.close()

    if row is None or row[0] != "ok":
        detail = None if row is None else row[0]
        raise BackupValidationError(
            f"SQLite integrity check did not pass: {detail!r}"
        )


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

    resolved = destination.expanduser().resolve()
    source_path = database.path.expanduser().resolve()
    if resolved == source_path:
        raise ValueError("backup destination cannot be the live database path")
    if resolved.exists():
        raise FileExistsError(f"refusing to overwrite existing backup: {resolved}")

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
            os.replace(temporary_archive, resolved)
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

    supported_versions = tuple(migration.version for migration in MIGRATIONS)
    expected_prefix = supported_versions[: len(actual_versions)]
    if actual_versions != expected_prefix:
        raise BackupValidationError(
            "backup database schema history is not a supported migration prefix"
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
    resolved_destination = destination.expanduser().resolve()

    if resolved_destination.exists():
        raise FileExistsError(
            f"refusing to overwrite existing database: {resolved_destination}"
        )

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
            database.migrate()
            _check_sqlite_integrity(staged)
            os.replace(staged, resolved_destination)
        finally:
            staged.unlink(missing_ok=True)

    return manifest
