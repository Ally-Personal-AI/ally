"""Verify and prepare a macOS Ally update without replacing the application."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import macos_update_trust
from ally.portability import BackupValidationError, create_backup, validate_backup
from ally.release.update_preparation import (
    PreMigrationBackupEvidence,
    UpdatePreparationError,
    UpdatePreparationRecord,
    prepare_update,
)
from ally.storage import default_database_path
from ally.storage.sqlite import SQLiteDatabase


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _create_backup_evidence(
    database: SQLiteDatabase,
    destination: Path,
) -> PreMigrationBackupEvidence:
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
    try:
        archive_sha256 = _sha256(destination.expanduser().resolve(strict=True))
    except OSError as exc:
        raise UpdatePreparationError(
            "pre-update backup could not be bound to the preparation record"
        ) from exc

    return PreMigrationBackupEvidence(
        archive_sha256=archive_sha256,
        database_sha256=validated.database.sha256,
        schema_versions=validated.database.schema_versions,
    )


def _render(record: UpdatePreparationRecord) -> str:
    payload: dict[str, Any] = asdict(record)
    payload["status"] = "prepared"
    return json.dumps(payload, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify a signed/notarized forward Ally.app candidate and satisfy "
            "pre-install backup requirements without replacing application code."
        )
    )
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--team-id", required=True)
    parser.add_argument(
        "--backup-output",
        type=Path,
        help=(
            "Fresh Ally backup path. Required when the candidate raises the "
            "database schema; optional otherwise."
        ),
    )
    parser.add_argument(
        "--database",
        type=Path,
        help=(
            "Database to back up; defaults to Ally's normal local database. "
            "Ignored unless --backup-output is supplied."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        decision = macos_update_trust.verify_update(
            args.current,
            args.candidate,
            expected_team_identifier=args.team_id,
        )
        backup_evidence = None
        if args.backup_output is not None:
            database = SQLiteDatabase(
                default_database_path() if args.database is None else args.database
            )
            backup_evidence = _create_backup_evidence(database, args.backup_output)
        record = prepare_update(decision, backup=backup_evidence)
        print(_render(record))
        return 0
    except (
        macos_update_trust.UpdateTrustError,
        UpdatePreparationError,
    ) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    raise SystemExit(main())
