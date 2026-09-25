from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest

from ally.release import ReleaseMetadata, compare_release_metadata
from ally.release.update_preparation import (
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


def _decision(*, schema_bump: bool) -> object:
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


def test_non_schema_update_can_be_prepared_without_touching_database(
    tmp_path: Path,
) -> None:
    decision = _decision(schema_bump=False)
    database_path = tmp_path / "must-not-exist.sqlite3"

    record = prepare_update(decision)

    assert record.schema_version == 1
    assert record.current_build_version == 7
    assert record.candidate_build_version == 8
    assert record.requires_pre_migration_backup is False
    assert record.backup_created is False
    assert record.backup_archive_sha256 is None
    assert not database_path.exists()


def test_schema_raising_update_requires_fresh_backup_destination() -> None:
    decision = _decision(schema_bump=True)

    with pytest.raises(UpdatePreparationError, match="fresh validated"):
        prepare_update(decision)


def test_schema_raising_update_creates_revalidates_and_binds_backup(
    tmp_path: Path,
) -> None:
    decision = _decision(schema_bump=True)
    database = SQLiteDatabase(tmp_path / "ally.sqlite3")
    backup = tmp_path / "before-update.ally-backup"

    record = prepare_update(
        decision,
        database=database,
        backup_destination=backup,
    )

    assert backup.is_file()
    assert record.requires_pre_migration_backup is True
    assert record.backup_created is True
    assert record.backup_archive_sha256 is not None
    assert len(record.backup_archive_sha256) == 64
    assert record.backup_database_sha256 is not None
    assert len(record.backup_database_sha256) == 64
    assert record.backup_schema_versions is not None
    assert record.backup_schema_versions[-1] == CURRENT_SCHEMA_VERSION

    rendered = json.dumps(asdict(record), sort_keys=True)
    assert str(tmp_path) not in rendered
    assert str(backup) not in rendered


def test_preparation_rejects_backup_that_does_not_match_release_schema(
    tmp_path: Path,
) -> None:
    decision = compare_release_metadata(
        _metadata(build=7, database_schema=CURRENT_SCHEMA_VERSION - 1),
        _metadata(
            build=8,
            database_schema=CURRENT_SCHEMA_VERSION,
            revision="b" * 40,
        ),
        expected_bundle_identifier="ai.ally.personal",
    )
    backup = tmp_path / "mismatch.ally-backup"

    with pytest.raises(UpdatePreparationError, match="installed release database schema"):
        prepare_update(
            decision,
            database=SQLiteDatabase(tmp_path / "ally.sqlite3"),
            backup_destination=backup,
        )

    assert backup.is_file()


def test_explicit_safety_backup_is_allowed_without_schema_bump(
    tmp_path: Path,
) -> None:
    decision = _decision(schema_bump=False)
    backup = tmp_path / "optional.ally-backup"

    record = prepare_update(
        decision,
        database=SQLiteDatabase(tmp_path / "ally.sqlite3"),
        backup_destination=backup,
    )

    assert record.requires_pre_migration_backup is False
    assert record.backup_created is True
    assert backup.is_file()
