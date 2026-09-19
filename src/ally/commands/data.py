"""Human-facing Ally data portability commands."""

from __future__ import annotations

from pathlib import Path

from ally.commands._storage import build_database
from ally.portability import (
    BackupValidationError,
    create_backup,
    restore_backup,
    validate_backup,
)
from ally.storage import default_database_path


def _print_manifest_summary(path: Path, *, ally_version: str, versions: tuple[int, ...]) -> None:
    version_text = ",".join(str(version) for version in versions) or "(none)"
    print(f"Archive: {path}")
    print(f"Created by Ally: {ally_version}")
    print(f"Database schema versions: {version_text}")


def run_data_backup(*, output: str) -> int:
    destination = Path(output).expanduser().resolve()
    try:
        manifest = create_backup(build_database(), destination)
    except (OSError, BackupValidationError) as exc:
        print(f"Backup error: {exc}")
        return 2

    _print_manifest_summary(
        destination,
        ally_version=manifest.ally_version,
        versions=manifest.database.schema_versions,
    )
    return 0


def run_validate_backup(*, archive: str) -> int:
    path = Path(archive).expanduser().resolve()
    try:
        manifest = validate_backup(path)
    except BackupValidationError as exc:
        print(f"Backup validation error: {exc}")
        return 2

    _print_manifest_summary(
        path,
        ally_version=manifest.ally_version,
        versions=manifest.database.schema_versions,
    )
    print("Backup validation: ok")
    return 0


def run_restore_backup(
    *,
    archive: str,
    destination: str | None,
) -> int:
    archive_path = Path(archive).expanduser().resolve()
    destination_path = (
        default_database_path()
        if destination is None
        else Path(destination).expanduser().resolve()
    )

    try:
        manifest = restore_backup(archive_path, destination_path)
    except (BackupValidationError, FileExistsError, OSError) as exc:
        print(f"Restore error: {exc}")
        return 2

    _print_manifest_summary(
        destination_path,
        ally_version=manifest.ally_version,
        versions=manifest.database.schema_versions,
    )
    return 0
