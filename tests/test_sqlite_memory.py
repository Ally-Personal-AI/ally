from datetime import UTC, datetime, timedelta
from pathlib import Path

from ally.memory import MemorySource, NewMemory
from ally.storage.sqlite import SQLiteDatabase, SQLiteMemoryStore


def build_store(path: Path) -> SQLiteMemoryStore:
    return SQLiteMemoryStore(SQLiteDatabase(path))


def test_memory_round_trip_preserves_provenance(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    record = store.create(
        NewMemory(
            kind="semantic",
            content="Synthetic project uses SQLite.",
            source=MemorySource(
                type="conversation",
                id="synthetic-message-id",
                uri="ally://conversation/synthetic",
            ),
            confidence=0.9,
            importance=0.8,
        )
    )

    loaded = store.get(record.id)

    assert loaded is not None
    assert loaded.content == record.content
    assert loaded.source.type == "conversation"
    assert loaded.source.id == "synthetic-message-id"
    assert loaded.source.uri == "ally://conversation/synthetic"
    assert loaded.confidence == 0.9
    assert loaded.importance == 0.8


def test_memory_validity_filters_by_time(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    future = datetime.now(UTC) + timedelta(days=2)
    record = store.create(
        NewMemory(
            kind="semantic",
            content="Synthetic future fact.",
            source=MemorySource(type="user"),
            valid_from=future,
        )
    )

    assert record not in store.list()
    assert record in store.list(as_of=future + timedelta(seconds=1))


def test_supersession_preserves_historical_truth(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    old = store.create(
        NewMemory(
            kind="preference",
            content="Prefers synthetic option A.",
            source=MemorySource(type="user"),
        )
    )
    updated_old, replacement = store.supersede(
        old.id,
        NewMemory(
            kind="preference",
            content="Prefers synthetic option B.",
            source=MemorySource(type="user"),
        ),
    )

    assert updated_old.superseded_at is not None
    midpoint = old.created_at + (updated_old.superseded_at - old.created_at) / 2

    historical = store.list(as_of=midpoint)
    current = store.list()

    assert old.id in {memory.id for memory in historical}
    assert replacement.id not in {memory.id for memory in historical}
    assert replacement.id in {memory.id for memory in current}
    assert old.id not in {memory.id for memory in current}


def test_retraction_hides_memory_but_keeps_audit_history(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    memory = store.create(
        NewMemory(
            kind="semantic",
            content="Synthetic retracted fact.",
            source=MemorySource(type="user"),
        )
    )

    retracted = store.retract(memory.id)

    assert retracted.retracted_at is not None
    assert memory.id not in {item.id for item in store.list()}
    assert memory.id in {
        item.id for item in store.list(include_inactive=True)
    }


def test_memory_search_only_returns_active_matches(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    active = store.create(
        NewMemory(
            kind="semantic",
            content="Synthetic orchard inventory.",
            source=MemorySource(type="user"),
        )
    )
    inactive = store.create(
        NewMemory(
            kind="semantic",
            content="Synthetic orchard obsolete note.",
            source=MemorySource(type="user"),
        )
    )
    store.retract(inactive.id)

    results = store.search("orchard")

    assert [item.id for item in results] == [active.id]
