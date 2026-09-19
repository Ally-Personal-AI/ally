from pathlib import Path
from uuid import UUID
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from ally.conversations import NewConversationMessage
from ally.events import NewEvent
from ally.portability import (
    BackupValidationError,
    create_backup,
    restore_backup,
    validate_backup,
)
from ally.storage.sqlite import (
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteEventStore,
)


def seed_database(path: Path) -> tuple[str, str]:
    database = SQLiteDatabase(path)
    conversations = SQLiteConversationStore(database)
    conversation = conversations.create(title="Synthetic")
    conversations.append_messages(
        conversation.id,
        (
            NewConversationMessage(role="user", content="hello"),
            NewConversationMessage(role="assistant", content="world"),
        ),
    )

    events = SQLiteEventStore(database)
    event = events.create(
        NewEvent(
            type="synthetic.event",
            source="test",
            importance="important",
            payload={"value": 1},
        ),
        attention="mention_later",
    )
    return str(conversation.id), str(event.id)


def test_backup_round_trip_preserves_ally_state(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    conversation_id, event_id = seed_database(source)
    archive = tmp_path / "state.ally-backup"

    manifest = create_backup(SQLiteDatabase(source), archive)
    validated = validate_backup(archive)

    assert validated == manifest
    assert manifest.database.schema_versions == (1, 2, 3, 4, 5, 6)

    with ZipFile(archive, mode="r") as bundle:
        assert set(bundle.namelist()) == {"manifest.json", "ally.sqlite3"}

    restored = tmp_path / "restored.sqlite3"
    restore_backup(archive, restored)

    conversation_store = SQLiteConversationStore(SQLiteDatabase(restored))
    event_store = SQLiteEventStore(SQLiteDatabase(restored))

    conversation = conversation_store.get(UUID(conversation_id))
    event = event_store.get(UUID(event_id))

    assert conversation is not None
    assert conversation.title == "Synthetic"
    assert [message.content for message in conversation_store.list_messages(conversation.id)] == [
        "hello",
        "world",
    ]
    assert event is not None
    assert event.payload == {"value": 1}
    assert event.attention == "mention_later"


def test_backup_validation_rejects_tampered_database(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    seed_database(source)
    archive = tmp_path / "state.ally-backup"
    create_backup(SQLiteDatabase(source), archive)

    with ZipFile(archive, mode="r") as original:
        manifest = original.read("manifest.json")
        database = original.read("ally.sqlite3")

    tampered = tmp_path / "tampered.ally-backup"
    with ZipFile(tampered, mode="w", compression=ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", manifest)
        bundle.writestr("ally.sqlite3", database + b"x")

    with pytest.raises(BackupValidationError, match="size|SHA-256"):
        validate_backup(tampered)


def test_backup_validation_rejects_unexpected_member(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    seed_database(source)
    archive = tmp_path / "state.ally-backup"
    create_backup(SQLiteDatabase(source), archive)

    with ZipFile(archive, mode="r") as original:
        manifest = original.read("manifest.json")
        database = original.read("ally.sqlite3")

    invalid = tmp_path / "unexpected.ally-backup"
    with ZipFile(invalid, mode="w", compression=ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", manifest)
        bundle.writestr("ally.sqlite3", database)
        bundle.writestr("secret.txt", "must not be accepted")

    with pytest.raises(BackupValidationError, match="exactly"):
        validate_backup(invalid)


def test_restore_refuses_to_overwrite_existing_database(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    seed_database(source)
    archive = tmp_path / "state.ally-backup"
    create_backup(SQLiteDatabase(source), archive)

    destination = tmp_path / "existing.sqlite3"
    destination.write_bytes(b"do not replace")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        restore_backup(archive, destination)

    assert destination.read_bytes() == b"do not replace"


def test_backup_refuses_to_overwrite_existing_archive(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    seed_database(source)
    archive = tmp_path / "state.ally-backup"
    archive.write_bytes(b"keep me")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        create_backup(SQLiteDatabase(source), archive)

    assert archive.read_bytes() == b"keep me"


def test_backup_refuses_live_database_as_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    seed_database(source)

    with pytest.raises(ValueError, match="live database"):
        create_backup(SQLiteDatabase(source), source)
