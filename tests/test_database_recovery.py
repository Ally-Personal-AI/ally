"""Upgrade and restore contracts for synthetic historical Ally databases."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from threading import Barrier
from typing import cast
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from ally.cli import main
from ally.portability import BackupValidationError, create_backup, restore_backup, validate_backup
from ally.portability import backup as backup_module
from ally.storage.errors import DatabaseMigrationError
from ally.storage.sqlite import SQLiteConversationStore, SQLiteDatabase
from ally.storage.sqlite.schema import MIGRATIONS, Migration

STAMP = "2026-01-01T00:00:00+00:00"
CONVERSATION_ID = "00000000-0000-0000-0000-000000000001"
MESSAGE_ID = "00000000-0000-0000-0000-000000000002"

# Recorded from main at 6876db3. Historical migration SQL and names are append-only.
# This makes the prefix fixtures below independent of later edits to old migrations.
RELEASED_NAMES = (
    "conversations", "memory_v1", "knowledge_v1", "tool_audit", "tasks_v1", "events_v1",
    "scheduler_v1", "attention_delivery_v1", "event_source_checkpoints_v1",
    "service_cycle_runs_v1", "skill_execution_audit_v1",
)
RELEASED_SQL_HASHES = (
    "ec954c8707506ed81af30687ed658e200acd9fdc8933178db316d08444816c4a",
    "1803f9da1d94f94d4c867aa8f4bc02144fe491426a8e4395c01311f906e99002",
    "3d88a0e5f0ca121d851eb928b11be383a61aa458cac2f4ef866727efa8206ac0",
    "5e91c9c643e2cb328196d0b4b31e0aabd499551da77e6352f4de787f2498ad56",
    "e827631e8cdcaa846eb38c4ca5562de8422fd6816cb8cd136e49fb81eb6cd289",
    "ab50692a358ede1aa137bf39968edc444c7bd67b29608991ed2296b8d123f6c7",
    "52cfe084bf2f569bc3dadeb822f1543ac7945068a0a9f2c46297d3b494da061c",
    "2488bb63029bb2d69ac2ac9d1e5e6f400f10bd498d3d8c7562df02d1bc9a9344",
    "b0799f7608fe7c5959a383016d101061c4dd5d7dc5272348f61da2e20d14372c",
    "e95ecfbc5c76a8f359e42f7457b80cef91600ab7a55af0c3d209dc0269f60ccb",
    "ae918eb935aa2e0b0a1a67ea57c1b50585b193366e68b9eff3edda31020a4b43",
)


def create_prefix(path: Path, count: int) -> None:
    """Create a historical database without calling the current migration runner."""

    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "CREATE TABLE ally_schema_migrations "
            "(version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        for migration in MIGRATIONS[:count]:
            for statement in migration.statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO ally_schema_migrations VALUES (?, ?, ?)",
                (migration.version, migration.name, STAMP),
            )
        if count:
            connection.execute(
                "INSERT INTO conversations VALUES (?, ?, ?, ?)",
                (CONVERSATION_ID, "Synthetic historical conversation", STAMP, STAMP),
            )
            connection.execute(
                "INSERT INTO conversation_messages VALUES (?, ?, ?, ?, ?, ?)",
                (MESSAGE_ID, CONVERSATION_ID, 0, "user", "Synthetic historical turn", STAMP),
            )


def dump(path: Path) -> str:
    with closing(sqlite3.connect(path)) as connection:
        return "\n".join(connection.iterdump())


def schema(path: Path) -> list[tuple[object, ...]]:
    with closing(sqlite3.connect(path)) as connection:
        entries = connection.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_schema "
            "WHERE name != 'ally_schema_migrations' ORDER BY type, name"
        ).fetchall()
        # Compare the metadata table structurally; its historical SQL formatting varies.
        entries.extend(connection.execute("PRAGMA table_info(ally_schema_migrations)").fetchall())
        return cast(list[tuple[object, ...]], entries)


def historical_archive(database: Path, archive: Path) -> None:
    """Package existing bytes directly, without the current backup/migration code."""

    data = database.read_bytes()
    with closing(sqlite3.connect(database)) as connection:
        versions = [row[0] for row in connection.execute(
            "SELECT version FROM ally_schema_migrations ORDER BY version"
        )]
    manifest = {
        "format": "ally-backup", "schema_version": 1, "created_at": STAMP,
        "ally_version": "0.1.0.dev0",
        "database": {
            "filename": "ally.sqlite3", "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data), "schema_versions": versions,
        },
    }
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest))
        bundle.writestr("ally.sqlite3", data)


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits required")
def test_new_database_is_owner_only_under_permissive_umask(tmp_path: Path) -> None:
    path = tmp_path / "private.sqlite3"
    previous_umask = os.umask(0)
    try:
        SQLiteDatabase(path).migrate()
    finally:
        os.umask(previous_umask)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits required")
def test_existing_database_permissions_are_tightened(tmp_path: Path) -> None:
    path = tmp_path / "existing.sqlite3"
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("CREATE TABLE synthetic(value TEXT)")
    path.chmod(0o666)

    with SQLiteDatabase(path).connect():
        pass

    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="POSIX mode bits required")
def test_sqlite_wal_sidecars_remain_owner_only(tmp_path: Path) -> None:
    path = tmp_path / "wal.sqlite3"
    previous_umask = os.umask(0)
    try:
        database = SQLiteDatabase(path)
        with database.connect() as connection:
            assert connection.execute("PRAGMA journal_mode = WAL").fetchone() == ("wal",)
            connection.execute("CREATE TABLE synthetic(value TEXT)")
            connection.execute("INSERT INTO synthetic VALUES ('private')")
            connection.commit()
            sidecars = (
                path.with_name(path.name + "-wal"),
                path.with_name(path.name + "-shm"),
            )
            assert any(sidecar.exists() for sidecar in sidecars)
            for sidecar in sidecars:
                if sidecar.exists():
                    assert stat.S_IMODE(sidecar.stat().st_mode) & 0o077 == 0
    finally:
        os.umask(previous_umask)


@pytest.mark.skipif(os.name != "posix", reason="POSIX file type semantics required")
def test_database_non_regular_file_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    os.mkfifo(path)

    with (
        pytest.raises(DatabaseMigrationError, match="private permissions"),
        SQLiteDatabase(path).connect(),
    ):
        pass


@pytest.mark.skipif(os.name != "posix", reason="POSIX symlink semantics required")
def test_database_final_symlink_is_refused(tmp_path: Path) -> None:
    target = tmp_path / "target.sqlite3"
    target.write_bytes(b"must not be touched")
    target.chmod(0o644)
    path = tmp_path / "ally.sqlite3"
    path.symlink_to(target)

    with (
        pytest.raises(DatabaseMigrationError, match="private permissions"),
        SQLiteDatabase(path).connect(),
    ):
        pass

    assert target.read_bytes() == b"must not be touched"
    assert stat.S_IMODE(target.stat().st_mode) == 0o644


def test_released_migrations_are_append_only() -> None:
    assert tuple(m.version for m in MIGRATIONS) == tuple(range(1, len(MIGRATIONS) + 1))
    released = MIGRATIONS[:len(RELEASED_NAMES)]
    assert tuple(m.name for m in released) == RELEASED_NAMES
    assert tuple(
        hashlib.sha256("\0".join(m.statements).encode()).hexdigest() for m in released
    ) == RELEASED_SQL_HASHES


@pytest.mark.parametrize("count", range(len(MIGRATIONS) + 1))
def test_every_historical_prefix_upgrades_and_restores(tmp_path: Path, count: int) -> None:
    source = tmp_path / "historical.sqlite3"
    create_prefix(source, count)
    archive = tmp_path / "historical.ally-backup"
    historical_archive(source, archive)
    original_archive = archive.read_bytes()
    current = tmp_path / "current.sqlite3"
    SQLiteDatabase(current).migrate()

    assert validate_backup(archive).database.schema_versions == tuple(range(1, count + 1))
    SQLiteDatabase(source).migrate()
    restored = tmp_path / "restored.sqlite3"
    restore_backup(archive, restored)

    assert archive.read_bytes() == original_archive
    for path in (source, restored):
        assert schema(path) == schema(current)
        before_retry = dump(path)
        SQLiteDatabase(path).migrate()
        assert dump(path) == before_retry
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM ally_schema_migrations WHERE applied_at = ?", (STAMP,),
            ).fetchone() == (count,)
        if count:
            store = SQLiteConversationStore(SQLiteDatabase(path))
            messages = store.list_messages(UUID(CONVERSATION_ID))
            assert [message.content for message in messages] == ["Synthetic historical turn"]


@pytest.mark.parametrize("count, successful_pending", [(0, 0), (6, 0), (6, 2)])
def test_failed_ddl_and_data_changes_roll_back_and_allow_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, count: int, successful_pending: int,
) -> None:
    path = tmp_path / "failed.sqlite3"
    if count:
        create_prefix(path, count)
    before = dump(path)
    failure_index = count + successful_pending
    pending = MIGRATIONS[failure_index]
    statements = (pending.statements[0],)
    if count:
        statements += ("UPDATE conversations SET title = 'must roll back'",)
    broken = Migration(
        pending.version, pending.name,
        (*statements, "SELECT value FROM synthetic_missing_table"),
    )
    with monkeypatch.context() as patch:
        patch.setattr(
            "ally.storage.sqlite.database.MIGRATIONS", (*MIGRATIONS[:failure_index], broken),
        )
        with pytest.raises(DatabaseMigrationError, match="no migration changes were committed"):
            SQLiteDatabase(path).migrate()
    assert dump(path) == before

    SQLiteDatabase(path).migrate()
    current = tmp_path / "fresh.sqlite3"
    SQLiteDatabase(current).migrate()
    assert schema(path) == schema(current)


@pytest.mark.parametrize("count", [0, 6])
def test_concurrent_starters_complete_one_upgrade(tmp_path: Path, count: int) -> None:
    path = tmp_path / "concurrent.sqlite3"
    create_prefix(path, count)
    ready = Barrier(4, timeout=10)

    def start() -> None:
        ready.wait()
        SQLiteDatabase(path).migrate()

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(start) for _ in range(4)]
        for future in futures:
            future.result(timeout=15)
    current = tmp_path / "fresh.sqlite3"
    SQLiteDatabase(current).migrate()
    assert schema(path) == schema(current)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM ally_schema_migrations").fetchone() == (
            len(MIGRATIONS),
        )


@pytest.mark.parametrize("mutation", [
    "INSERT INTO ally_schema_migrations VALUES (99, 'private-marker', 'future')",
    "DELETE FROM ally_schema_migrations WHERE version = 2",
    "UPDATE ally_schema_migrations SET name = 'private-marker' WHERE version = 1",
    "DROP TABLE ally_schema_migrations",
    "DELETE FROM ally_schema_migrations",
])
def test_incompatible_history_is_refused_without_changes(tmp_path: Path, mutation: str) -> None:
    path = tmp_path / "incompatible.sqlite3"
    create_prefix(path, len(MIGRATIONS))
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(mutation)
    before = dump(path)
    with pytest.raises(DatabaseMigrationError) as error:
        SQLiteDatabase(path).migrate()
    assert "private-marker" not in str(error.value)
    assert dump(path) == before


def test_cli_reports_incompatible_history_without_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    path = tmp_path / "incompatible.sqlite3"
    create_prefix(path, 1)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("UPDATE ally_schema_migrations SET name = 'private-marker'")
    monkeypatch.setattr(
        "ally.composition.defaults.default_database_path",
        lambda: path,
    )
    before = dump(path)
    assert main(["conversations", "list"]) == 2
    output = capsys.readouterr()
    assert "Database error:" in output.out
    assert "compatible version" in output.out
    assert "private-marker" not in output.out
    assert output.err == ""
    assert dump(path) == before


def test_archive_rejects_renamed_migration_despite_matching_versions(tmp_path: Path) -> None:
    path = tmp_path / "renamed.sqlite3"
    create_prefix(path, 1)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("UPDATE ally_schema_migrations SET name = 'private-marker'")
    archive = tmp_path / "renamed.ally-backup"
    historical_archive(path, archive)
    with pytest.raises(BackupValidationError, match="schema metadata"):
        validate_backup(archive)


def test_archives_reject_orphaned_references_without_printing_data(tmp_path: Path) -> None:
    path = tmp_path / "orphan.sqlite3"
    create_prefix(path, 1)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute(
            "INSERT INTO conversation_messages VALUES (?, ?, ?, ?, ?, ?)",
            ("synthetic-orphan", "absent-parent", 0, "user", "private-marker", STAMP),
        )
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    archive = tmp_path / "orphan.ally-backup"
    historical_archive(path, archive)
    with pytest.raises(BackupValidationError, match="foreign-key") as error:
        validate_backup(archive)
    assert "private-marker" not in str(error.value)
    destination = tmp_path / "refused.sqlite3"
    with pytest.raises(BackupValidationError):
        restore_backup(archive, destination)
    assert not destination.exists()
    new_archive = tmp_path / "refused.ally-backup"
    with pytest.raises(BackupValidationError):
        create_backup(SQLiteDatabase(path), new_archive)
    assert not new_archive.exists()


def test_failed_restore_upgrade_does_not_publish_or_change_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "historical.sqlite3"
    create_prefix(source, 6)
    archive = tmp_path / "historical.ally-backup"
    historical_archive(source, archive)
    before = archive.read_bytes()
    migration = MIGRATIONS[6]
    broken = Migration(7, migration.name, (migration.statements[0], "SELECT missing FROM absent"))
    monkeypatch.setattr("ally.storage.sqlite.database.MIGRATIONS", (*MIGRATIONS[:6], broken))
    destination = tmp_path / "restored.sqlite3"
    with pytest.raises(BackupValidationError, match="could not be upgraded"):
        restore_backup(archive, destination)
    assert archive.read_bytes() == before
    assert not destination.exists()
    assert not list(tmp_path.glob(".*.restore*"))


@pytest.mark.parametrize("operation", ["backup", "restore"])
@pytest.mark.parametrize("symlink", [False, True])
def test_publication_cannot_clobber_a_competing_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, operation: str, symlink: bool,
) -> None:
    source = tmp_path / "source.sqlite3"
    create_prefix(source, len(MIGRATIONS))
    archive = tmp_path / "source.ally-backup"
    historical_archive(source, archive)
    destination = tmp_path / "competing-destination"
    other = tmp_path / "other-writers-file"
    marker = b"synthetic other writer's data"
    check = backup_module._check_sqlite_integrity  # pyright: ignore[reportPrivateUsage]

    def competing_write(path: Path) -> None:
        check(path)
        if not destination.exists():
            if symlink:
                other.write_bytes(marker)
                destination.symlink_to(other)
            else:
                destination.write_bytes(marker)

    monkeypatch.setattr(backup_module, "_check_sqlite_integrity", competing_write)
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        if operation == "backup":
            create_backup(SQLiteDatabase(source), destination)
        else:
            restore_backup(archive, destination)
    assert destination.read_bytes() == marker
    assert destination.is_symlink() is symlink
    assert not list(tmp_path.glob(".*.tmp"))
    assert not list(tmp_path.glob(".*.restore*"))


@pytest.mark.parametrize("operation", ["backup", "restore"])
def test_cli_refuses_dangling_destination_symlinks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
    operation: str,
) -> None:
    source = tmp_path / "source.sqlite3"
    create_prefix(source, len(MIGRATIONS))
    archive = tmp_path / "source.ally-backup"
    historical_archive(source, archive)
    target = tmp_path / "must-not-be-created"
    destination = tmp_path / "occupied"
    destination.symlink_to(target)
    monkeypatch.setattr("ally.commands._storage.default_database_path", lambda: source)
    arguments = (
        ["data", "backup", str(destination)] if operation == "backup"
        else ["data", "restore", str(archive), "--destination", str(destination)]
    )
    assert main(arguments) == 2
    assert "refusing to overwrite" in capsys.readouterr().out
    assert destination.is_symlink()
    assert not target.exists()


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_restore_refuses_leftover_sqlite_sidecars(tmp_path: Path, suffix: str) -> None:
    source = tmp_path / "source.sqlite3"
    create_prefix(source, 1)
    archive = tmp_path / "source.ally-backup"
    historical_archive(source, archive)
    destination = tmp_path / "restored.sqlite3"
    sidecar = destination.with_name(destination.name + suffix)
    marker = b"synthetic recovery state"
    sidecar.write_bytes(marker)
    with pytest.raises(FileExistsError, match="existing SQLite sidecars"):
        restore_backup(archive, destination)
    assert sidecar.read_bytes() == marker
    assert not destination.exists()


def test_unsupported_publication_fails_without_a_partial_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "source.sqlite3"
    create_prefix(source, 1)
    archive = tmp_path / "source.ally-backup"
    historical_archive(source, archive)
    destination = tmp_path / "restored.sqlite3"

    def unsupported(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic filesystem without hard links")

    monkeypatch.setattr("ally.portability.backup.os.link", unsupported)
    with pytest.raises(OSError, match="without hard links"):
        restore_backup(archive, destination)
    assert not destination.exists()
    assert not list(tmp_path.glob(".*.restore*"))
