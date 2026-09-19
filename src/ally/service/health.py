"""Deterministic local service health reporting."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ally.service.models import ServiceHealthReport
from ally.service.store import ServiceCycleRunStore
from ally.storage.sqlite.schema import MIGRATIONS


def build_service_health(
    *,
    database_path: Path,
    runs: ServiceCycleRunStore | None,
) -> ServiceHealthReport:
    expected = tuple(migration.version for migration in MIGRATIONS)
    if not database_path.exists():
        return ServiceHealthReport(
            status="uninitialized",
            database_exists=False,
            database_integrity_ok=False,
            schema_current=False,
            expected_schema_versions=expected,
        )

    integrity_ok = False
    versions: tuple[int, ...] = ()
    try:
        connection = sqlite3.connect(
            f"file:{database_path}?mode=ro",
            uri=True,
        )
        try:
            row = connection.execute("PRAGMA quick_check").fetchone()
            integrity_ok = bool(row and row[0] == "ok")
            migration_rows = connection.execute(
                """
                SELECT version
                FROM ally_schema_migrations
                ORDER BY version
                """
            ).fetchall()
            versions = tuple(int(item[0]) for item in migration_rows)
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        integrity_ok = False

    schema_current = versions == expected
    latest = runs.latest() if runs is not None and integrity_ok else None

    if not integrity_ok or not schema_current:
        status = "degraded"
    elif latest is None:
        status = "uninitialized"
    elif latest.status in ("failed", "degraded", "interrupted"):
        status = "degraded"
    else:
        status = "healthy"

    return ServiceHealthReport(
        status=status,
        database_exists=True,
        database_integrity_ok=integrity_ok,
        schema_current=schema_current,
        applied_schema_versions=versions,
        expected_schema_versions=expected,
        latest_cycle=latest,
    )
