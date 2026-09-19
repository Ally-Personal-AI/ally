"""Ephemeral cross-process service coordination leases."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

_LEASE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("service lease timestamp must include a timezone offset")
    return value.astimezone(UTC)


def validate_lease_name(value: str) -> str:
    if _LEASE_NAME_PATTERN.fullmatch(value) is None:
        raise ValueError(f"invalid service lease name: {value}")
    return value


class ServiceLeaseUnavailableError(RuntimeError):
    """Raised when another owner currently holds a non-expired lease."""


class ServiceLeaseRecord(BaseModel):
    """One ephemeral coordination lease."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(
        min_length=1,
        pattern=r"^[a-z0-9][a-z0-9_.-]*$",
    )
    owner_id: UUID
    acquired_at: datetime
    expires_at: datetime
    updated_at: datetime

    @field_validator("acquired_at", "expires_at", "updated_at")
    @classmethod
    def validate_timestamps(cls, value: datetime) -> datetime:
        return _as_utc(value)


LeaseRow = tuple[str, str, str, str, str]


class SQLiteServiceLeaseStore:
    """Small disposable SQLite database for service coordination."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser().resolve()
        self._initialize()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=5.0)
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS service_leases (
                    name TEXT PRIMARY KEY,
                    owner_id TEXT NOT NULL,
                    acquired_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )

    def acquire(
        self,
        *,
        name: str,
        owner_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> ServiceLeaseRecord | None:
        validated = validate_lease_name(name)
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")

        observed_at = _as_utc(now)
        expires_at = observed_at + timedelta(seconds=ttl_seconds)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT
                    name,
                    owner_id,
                    acquired_at,
                    expires_at,
                    updated_at
                FROM service_leases
                WHERE name = ?
                """,
                (validated,),
            ).fetchone()

            if row is None:
                connection.execute(
                    """
                    INSERT INTO service_leases(
                        name,
                        owner_id,
                        acquired_at,
                        expires_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        validated,
                        str(owner_id),
                        observed_at.isoformat(),
                        expires_at.isoformat(),
                        observed_at.isoformat(),
                    ),
                )
            else:
                current = self._from_row(cast(LeaseRow, row))
                if (
                    current.owner_id != owner_id
                    and current.expires_at > observed_at
                ):
                    return None

                connection.execute(
                    """
                    UPDATE service_leases
                    SET
                        owner_id = ?,
                        acquired_at = ?,
                        expires_at = ?,
                        updated_at = ?
                    WHERE name = ?
                    """,
                    (
                        str(owner_id),
                        observed_at.isoformat(),
                        expires_at.isoformat(),
                        observed_at.isoformat(),
                        validated,
                    ),
                )

        return self.get(validated)

    def renew(
        self,
        *,
        name: str,
        owner_id: UUID,
        now: datetime,
        ttl_seconds: int,
    ) -> ServiceLeaseRecord | None:
        validated = validate_lease_name(name)
        if ttl_seconds < 1:
            raise ValueError("ttl_seconds must be positive")

        observed_at = _as_utc(now)
        expires_at = observed_at + timedelta(seconds=ttl_seconds)

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT
                    name,
                    owner_id,
                    acquired_at,
                    expires_at,
                    updated_at
                FROM service_leases
                WHERE name = ?
                """,
                (validated,),
            ).fetchone()

            if row is None:
                return None

            current = self._from_row(cast(LeaseRow, row))
            if (
                current.owner_id != owner_id
                or current.expires_at <= observed_at
            ):
                return None

            connection.execute(
                """
                UPDATE service_leases
                SET expires_at = ?, updated_at = ?
                WHERE name = ? AND owner_id = ?
                """,
                (
                    expires_at.isoformat(),
                    observed_at.isoformat(),
                    validated,
                    str(owner_id),
                ),
            )

        return self.get(validated)

    def release(self, *, name: str, owner_id: UUID) -> bool:
        validated = validate_lease_name(name)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM service_leases
                WHERE name = ? AND owner_id = ?
                """,
                (validated, str(owner_id)),
            )
            return cursor.rowcount == 1

    def get(self, name: str) -> ServiceLeaseRecord | None:
        validated = validate_lease_name(name)
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    name,
                    owner_id,
                    acquired_at,
                    expires_at,
                    updated_at
                FROM service_leases
                WHERE name = ?
                """,
                (validated,),
            ).fetchone()

        if row is None:
            return None
        return self._from_row(cast(LeaseRow, row))

    def list(self) -> tuple[ServiceLeaseRecord, ...]:
        with self._connect() as connection:
            rows = cast(
                list[LeaseRow],
                connection.execute(
                    """
                    SELECT
                        name,
                        owner_id,
                        acquired_at,
                        expires_at,
                        updated_at
                    FROM service_leases
                    ORDER BY name ASC
                    """
                ).fetchall(),
            )
        return tuple(self._from_row(row) for row in rows)

    @staticmethod
    def _from_row(row: LeaseRow) -> ServiceLeaseRecord:
        name, owner_id, acquired_at, expires_at, updated_at = row
        return ServiceLeaseRecord(
            name=name,
            owner_id=UUID(owner_id),
            acquired_at=datetime.fromisoformat(acquired_at),
            expires_at=datetime.fromisoformat(expires_at),
            updated_at=datetime.fromisoformat(updated_at),
        )


@contextmanager
def service_lease(
    store: SQLiteServiceLeaseStore,
    *,
    name: str,
    ttl_seconds: int,
    owner_id: UUID | None = None,
) -> Generator[ServiceLeaseRecord, None, None]:
    """Acquire an ephemeral lease and release it on scope exit."""

    owner = owner_id or uuid4()
    acquired = store.acquire(
        name=name,
        owner_id=owner,
        now=datetime.now(UTC),
        ttl_seconds=ttl_seconds,
    )
    if acquired is None:
        raise ServiceLeaseUnavailableError(
            f"service lease is already held: {name}"
        )

    try:
        yield acquired
    finally:
        store.release(name=name, owner_id=owner)
