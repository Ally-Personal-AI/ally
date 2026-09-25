"""Fail-closed preparation for a verified Ally application update."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from ally.portability import (
    BackupManifest,
    BackupValidationError,
    create_backup,
    validate_backup,
)
from ally.release.update_trust import UpdateDecision
from ally.storage.sqlite import SQLiteDatabase


class UpdatePreparationError(RuntimeError):
    """Raised when a verified update cannot satisfy pre-install safety gates."""


@dataclass(frozen=True)
class UpdatePreparationRecord:
    """Path-free evidence that update prerequisites were satisfied."""

    schema_version: int
    current_build_version: int
    candidate_build_version: int
    current_ally_version: str
    candidate_ally_version: str
    current_database_schema_version: int
    candidate_database_schema_version: int
    candidate_source_revision: str
    requires_pre_migration_backup: bool
    backup_created: bool
    backup_archive_sha256: str | None
    backup_database_sha256: str | None
    backup_schema_versions: tuple[int, ...] | None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _record(
    decision: UpdateDecision,
    *,
    backup_manifest: BackupManifest | None = None,
    backup_archive_sha256: str | None = None,
) -> UpdatePreparationRecord:
    return UpdatePreparationRecord(
        schema_version=1,
        current_build_version=decision.current_build_version,
        candidate_build_version=decision.candidate_build_version,
        current_ally_version=decision.current_ally_version,
        candidate_ally_version=decision.candidate_ally_version,
        current_database_schema_version=decision.current_database_schema_version,
        candidate_database_schema_version=decision.candidate_database_schema_version,
        candidate_source_revision=decision.candidate_source_revision,
        requires_pre_migration_backup=decision.requires_pre_migration_backup,
        backup_created=backup_manifest is not None,
        backup_archive_sha256=backup_archive_sha256,
        backup_database_sha256=(
            None if backup_manifest is None else backup_manifest.database.sha256
        ),
        backup_schema_versions=(
            None if backup_manifest is None else backup_manifest.database.schema_versions
        ),
    )


def _require_backup_matches_installed_release(
    manifest: BackupManifest,
    decision: UpdateDecision,
) -> None:
    versions = manifest.database.schema_versions
    if not versions:
        raise UpdatePreparationError(
            "pre-update backup has no Ally database schema history"
        )
    if versions[-1] != decision.current_database_schema_version:
        raise UpdatePreparationError(
            "pre-update backup does not match the installed release database schema"
        )


def prepare_update(
    decision: UpdateDecision,
    *,
    database: SQLiteDatabase | None = None,
    backup_destination: Path | None = None,
) -> UpdatePreparationRecord:
    """Satisfy pre-install data-safety requirements without replacing application code.

    The caller must supply an UpdateDecision produced by the trusted candidate
    verification boundary. This function never authenticates application code,
    fetches releases, or replaces an app bundle.

    A schema-raising update is not considered prepared unless a fresh Ally backup
    is created, re-opened through the normal validation boundary, and confirmed to
    match the installed release's database-schema contract.
    """

    if decision.requires_pre_migration_backup and backup_destination is None:
        raise UpdatePreparationError(
            "schema-raising update requires a fresh validated pre-migration backup"
        )

    if backup_destination is None:
        return _record(decision)

    if database is None:
        raise UpdatePreparationError(
            "a database is required when creating a pre-update backup"
        )

    destination = backup_destination.expanduser()
    try:
        created = create_backup(database, destination)
        validated = validate_backup(destination)
    except (
        BackupValidationError,
        FileExistsError,
        OSError,
        ValueError,
    ) as exc:
        raise UpdatePreparationError(
            "pre-update backup could not be created and validated"
        ) from exc

    if created != validated:
        raise UpdatePreparationError(
            "pre-update backup changed between creation and validation"
        )
    _require_backup_matches_installed_release(validated, decision)

    try:
        archive_sha256 = _sha256(destination.resolve(strict=True))
    except OSError as exc:
        raise UpdatePreparationError(
            "pre-update backup could not be bound to the preparation record"
        ) from exc

    return _record(
        decision,
        backup_manifest=validated,
        backup_archive_sha256=archive_sha256,
    )
