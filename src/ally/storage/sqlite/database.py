"""SQLite database lifecycle and schema migrations."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from ally.storage.errors import DatabaseMigrationError
from ally.storage.sqlite.schema import MIGRATIONS


def _prepare_private_database_file(path: Path) -> None:
    """Create/tighten one Ally database inode before SQLite writes private state."""

    if os.name != "posix":
        return

    flags = os.O_RDWR | os.O_CREAT
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise DatabaseMigrationError(
            "Database file could not be prepared with private permissions."
        ) from exc
    try:
        os.fchmod(descriptor, 0o600)
    except OSError as exc:
        raise DatabaseMigrationError(
            "Database file could not be prepared with private permissions."
        ) from exc
    finally:
        os.close(descriptor)


def read_schema_versions(connection: sqlite3.Connection) -> tuple[int, ...]:
    """Require recorded versions and names to be a supported migration prefix."""

    rows = cast(
        list[tuple[int, str]],
        connection.execute(
            "SELECT version, name FROM ally_schema_migrations ORDER BY version"
        ).fetchall(),
    )
    expected = tuple((migration.version, migration.name) for migration in MIGRATIONS)
    if tuple(rows) != expected[: len(rows)]:
        raise DatabaseMigrationError(
            "Database migration history is not supported by this Ally version. "
            "Use a compatible version or restore a validated backup to a new path."
        )
    return tuple(row[0] for row in rows)


class SQLiteDatabase:
    """Owns connections and migrations for Ally's local SQLite database."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _prepare_private_database_file(self.path)
        # CPython accepts this sentinel; the current sqlite3 stub types it as bool only.
        connection = sqlite3.connect(
            self.path,
            autocommit=sqlite3.LEGACY_TRANSACTION_CONTROL,  # pyright: ignore[reportArgumentType]
        )
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def migrate(self) -> None:
        """Commit all pending migrations together, after acquiring the writer lock."""

        try:
            with self.connect() as connection:
                # DDL is not implicitly transactional in sqlite3's legacy mode.
                # Lock before reading history so concurrent starters see a fresh prefix.
                connection.execute("BEGIN IMMEDIATE")
                has_history = connection.execute(
                    "SELECT 1 FROM sqlite_schema "
                    "WHERE type = 'table' AND name = 'ally_schema_migrations'"
                ).fetchone() is not None
                if not has_history and connection.execute(
                    "SELECT 1 FROM sqlite_schema WHERE name NOT GLOB 'sqlite_*' LIMIT 1"
                ).fetchone() is not None:
                    raise DatabaseMigrationError(
                        "Database contains objects without Ally migration history. "
                        "Preserve the database and restore a validated backup to a new path."
                    )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ally_schema_migrations (
                        version INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                applied = read_schema_versions(connection)
                for migration in MIGRATIONS[len(applied):]:
                    for statement in migration.statements:
                        connection.execute(statement)
                    connection.execute(
                        """
                        INSERT INTO ally_schema_migrations(version, name, applied_at)
                        VALUES (?, ?, ?)
                        """,
                        (
                            migration.version,
                            migration.name,
                            datetime.now(UTC).isoformat(),
                        ),
                    )
        except sqlite3.DatabaseError as exc:
            raise DatabaseMigrationError(
                "Database upgrade failed; no migration changes were committed. "
                "Check database access and other running Ally processes before retrying."
            ) from exc
