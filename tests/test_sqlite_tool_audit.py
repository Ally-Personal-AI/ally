import pytest

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ally.storage.sqlite import SQLiteDatabase, SQLiteToolAuditStore
from ally.tools.audit import ToolAuditRecord


def test_tool_audit_round_trips_locally(tmp_path: Path) -> None:
    path = tmp_path / "ally.sqlite3"
    store = SQLiteToolAuditStore(SQLiteDatabase(path))
    now = datetime.now(UTC)
    record = ToolAuditRecord(
        id=uuid4(),
        invocation_id=uuid4(),
        tool_name="system.info",
        risk="read_only",
        decision="allow",
        status="succeeded",
        arguments={},
        output={"platform": "synthetic"},
        started_at=now,
        finished_at=now,
    )

    store.append(record)

    reopened = SQLiteToolAuditStore(SQLiteDatabase(path))
    loaded = reopened.list()

    assert len(loaded) == 1
    assert loaded[0] == record


def test_tool_audit_rejects_non_positive_limit(tmp_path: Path) -> None:
    store = SQLiteToolAuditStore(SQLiteDatabase(tmp_path / "ally.sqlite3"))

    with pytest.raises(ValueError, match="positive"):
        store.list(limit=0)
