"""Fail-closed preparation policy for a verified Ally application update."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ally.release.update_trust import UpdateDecision

_SHA256_RE = re.compile(r"[0-9a-f]{64}")


class UpdatePreparationError(RuntimeError):
    """Raised when a verified update cannot satisfy pre-install safety gates."""


@dataclass(frozen=True)
class PreMigrationBackupEvidence:
    """Path-free evidence produced after creating and revalidating a fresh backup."""

    archive_sha256: str
    database_sha256: str
    schema_versions: tuple[int, ...]


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


def _require_valid_backup_evidence(
    evidence: PreMigrationBackupEvidence,
    decision: UpdateDecision,
) -> None:
    if _SHA256_RE.fullmatch(evidence.archive_sha256) is None:
        raise UpdatePreparationError("pre-update backup archive digest is invalid")
    if _SHA256_RE.fullmatch(evidence.database_sha256) is None:
        raise UpdatePreparationError("pre-update backup database digest is invalid")
    if not evidence.schema_versions:
        raise UpdatePreparationError(
            "pre-update backup has no Ally database schema history"
        )
    if evidence.schema_versions[-1] != decision.current_database_schema_version:
        raise UpdatePreparationError(
            "pre-update backup does not match the installed release database schema"
        )


def prepare_update(
    decision: UpdateDecision,
    *,
    backup: PreMigrationBackupEvidence | None = None,
) -> UpdatePreparationRecord:
    """Apply update-preparation policy without authenticating or replacing code.

    The caller must supply an UpdateDecision produced by the trusted candidate
    verification boundary. Backup evidence must be produced by an infrastructure
    edge after creating and revalidating a fresh Ally backup.

    This policy performs no filesystem access, release fetching, application
    replacement, database migration, or rollback.
    """

    if decision.requires_pre_migration_backup and backup is None:
        raise UpdatePreparationError(
            "schema-raising update requires a fresh validated pre-migration backup"
        )
    if backup is not None:
        _require_valid_backup_evidence(backup, decision)

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
        backup_created=backup is not None,
        backup_archive_sha256=None if backup is None else backup.archive_sha256,
        backup_database_sha256=None if backup is None else backup.database_sha256,
        backup_schema_versions=None if backup is None else backup.schema_versions,
    )
