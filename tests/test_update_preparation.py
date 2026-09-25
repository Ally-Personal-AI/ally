from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from ally.portability import create_backup, validate_backup
from ally.release import ReleaseMetadata, UpdateDecision, compare_release_metadata
from ally.release.update_preparation import (
    PreMigrationBackupEvidence,
    UpdatePreparationError,
    prepare_update,
)
from ally.storage.sqlite import SQLiteDatabase
from ally.storage.sqlite.schema import CURRENT_SCHEMA_VERSION


def _metadata(
    *,
    build: int,
    database_schema: int = CURRENT_SCHEMA_VERSION,
    revision: str = "a" * 40,
) -> ReleaseMetadata:
    return ReleaseMetadata(
        bundle_identifier="ai.ally.personal",
        ally_version="0.1.0",
        short_version=(0, 1, 0),
        build_version=build,
        bridge_protocol_version=7,
        database_schema_version=database_schema,
        source_revision=revision,
    )


def _decision(*, schema_bump: bool) -> UpdateDecision:
    candidate_schema = CURRENT_SCHEMA_VERSION + 1 if schema_bump else CURRENT_SCHEMA_VERSION
    return compare_release_metadata(
        _metadata(build=7),
        _metadata(
            build=8,
            database_schema=candidate_schema,
            revision="b" * 40,
        ),
        expected_bundle_identifier="ai.ally.personal",
    )


def _fresh_backup_evidence(
    tmp_path: Path,
) -> tuple[PreMigrationBackupEvidence, Path]:
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    backup = tmp_path / "before-update.ally-backup"
    created = create_backup(database, backup)
    validated = validate_backup(backup)
    assert validated == created
    return (
        PreMigrationBackupEvidence(
            archive_sha256=hashlib.sha256(backup.read_bytes()).hexdigest(),
            database_sha256=validated.database.sha256,
            schema_versions=validated.database.schema_versions,
        ),
        backup,
    )


def test_non_schema_update_can_be_prepared_without_backup() -> None:
    record = prepare_update(_decision(schema_bump=False))

    assert record.schema_version == 1
    assert record.current_build_version == 7
    assert record.candidate_build_version == 8
    assert record.requires_pre_migration_backup is False
    assert record.backup_created is False
    assert record.backup_archive_sha256 is None


def test_schema_raising_update_requires_fresh_backup_evidence() -> None:
    with pytest.raises(UpdatePreparationError, match="fresh validated"):
        prepare_update(_decision(schema_bump=True))


def test_schema_raising_update_accepts_revalidated_path_free_backup_evidence(
    tmp_path: Path,
) -> None:
    evidence, backup = _fresh_backup_evidence(tmp_path)

    record = prepare_update(_decision(schema_bump=True), backup=evidence)

    assert backup.is_file()
    assert record.requires_pre_migration_backup is True
    assert record.backup_created is True
    assert record.backup_archive_sha256 == evidence.archive_sha256
    assert record.backup_database_sha256 == evidence.database_sha256
    assert record.backup_schema_versions is not None
    assert record.backup_schema_versions[-1] == CURRENT_SCHEMA_VERSION

    rendered = json.dumps(asdict(record), sort_keys=True)
    assert str(tmp_path) not in rendered
    assert str(backup) not in rendered


def test_preparation_rejects_backup_that_does_not_match_release_schema() -> None:
    decision = compare_release_metadata(
        _metadata(build=7, database_schema=CURRENT_SCHEMA_VERSION - 1),
        _metadata(
            build=8,
            database_schema=CURRENT_SCHEMA_VERSION,
            revision="b" * 40,
        ),
        expected_bundle_identifier="ai.ally.personal",
    )
    evidence = PreMigrationBackupEvidence(
        archive_sha256="a" * 64,
        database_sha256="b" * 64,
        schema_versions=tuple(range(1, CURRENT_SCHEMA_VERSION + 1)),
    )

    with pytest.raises(UpdatePreparationError, match="installed release database schema"):
        prepare_update(decision, backup=evidence)


@pytest.mark.parametrize(
    ("archive_digest", "database_digest", "message"),
    [
        ("not-a-digest", "b" * 64, "archive digest"),
        ("a" * 64, "not-a-digest", "database digest"),
    ],
)
def test_preparation_rejects_invalid_backup_hash_evidence(
    archive_digest: str,
    database_digest: str,
    message: str,
) -> None:
    evidence = PreMigrationBackupEvidence(
        archive_sha256=archive_digest,
        database_sha256=database_digest,
        schema_versions=tuple(range(1, CURRENT_SCHEMA_VERSION + 1)),
    )

    with pytest.raises(UpdatePreparationError, match=message):
        prepare_update(_decision(schema_bump=True), backup=evidence)


def test_explicit_safety_backup_is_allowed_without_schema_bump(
    tmp_path: Path,
) -> None:
    evidence, backup = _fresh_backup_evidence(tmp_path)

    record = prepare_update(_decision(schema_bump=False), backup=evidence)

    assert record.requires_pre_migration_backup is False
    assert record.backup_created is True
    assert backup.is_file()
