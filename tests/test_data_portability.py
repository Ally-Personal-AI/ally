from datetime import UTC, datetime
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
from ally.scheduler import NewSchedule
from ally.skills import SkillExecutionResult
from ally.storage.sqlite import (
    SQLiteAttentionDeliveryStore,
    SQLiteConversationStore,
    SQLiteDatabase,
    SQLiteEventSourceCheckpointStore,
    SQLiteEventStore,
    SQLiteScheduleStore,
    SQLiteServiceCycleRunStore,
    SQLiteSkillExecutionAuditStore,
)


def seed_database(path: Path) -> tuple[str, str, str]:
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

    deliveries = SQLiteAttentionDeliveryStore(database)
    deliveries.record_attempt(
        event_id=event.id,
        sink_id="backup-test",
        succeeded=True,
    )

    source_checkpoints = SQLiteEventSourceCheckpointStore(database)
    source_checkpoints.advance(
        source_id="backup.source",
        expected_cursor=None,
        next_cursor="cursor-1",
        published=1,
        polled_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )

    service_runs = SQLiteServiceCycleRunStore(database)
    run_started = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    service_run = service_runs.start(
        observed_at=run_started,
        started_at=run_started,
    )
    service_runs.finish(
        service_run.id,
        status="succeeded",
        finished_at=run_started,
    )

    skill_audit = SQLiteSkillExecutionAuditStore(database)
    audit_time = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    skill_audit.record(
        installation_id=UUID("00000000-0000-0000-0000-000000000123"),
        result=SkillExecutionResult(
            skill_id="backup.skill",
            version="1.0.0",
            status="succeeded",
            result={"synthetic": "result-not-audited"},
            exit_code=0,
            started_at=audit_time,
            finished_at=audit_time,
            duration_ms=0,
        ),
    )

    schedules = SQLiteScheduleStore(database)
    schedule = schedules.create(
        NewSchedule(
            name="Synthetic schedule",
            event_type="synthetic.scheduled",
            starts_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
            interval_seconds=300,
        )
    )
    return str(conversation.id), str(event.id), str(schedule.id)


def test_backup_round_trip_preserves_ally_state(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    conversation_id, event_id, schedule_id = seed_database(source)
    archive = tmp_path / "state.ally-backup"

    manifest = create_backup(SQLiteDatabase(source), archive)
    validated = validate_backup(archive)

    assert validated == manifest
    assert manifest.database.schema_versions == (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11)

    with ZipFile(archive, mode="r") as bundle:
        assert set(bundle.namelist()) == {"manifest.json", "ally.sqlite3"}

    restored = tmp_path / "restored.sqlite3"
    restore_backup(archive, restored)

    conversation_store = SQLiteConversationStore(SQLiteDatabase(restored))
    event_store = SQLiteEventStore(SQLiteDatabase(restored))
    source_checkpoint_store = SQLiteEventSourceCheckpointStore(
        SQLiteDatabase(restored)
    )
    delivery_store = SQLiteAttentionDeliveryStore(SQLiteDatabase(restored))
    schedule_store = SQLiteScheduleStore(SQLiteDatabase(restored))
    service_run_store = SQLiteServiceCycleRunStore(SQLiteDatabase(restored))
    skill_audit_store = SQLiteSkillExecutionAuditStore(SQLiteDatabase(restored))

    conversation = conversation_store.get(UUID(conversation_id))
    event = event_store.get(UUID(event_id))
    schedule = schedule_store.get(UUID(schedule_id))

    assert conversation is not None
    assert conversation.title == "Synthetic"
    assert [message.content for message in conversation_store.list_messages(conversation.id)] == [
        "hello",
        "world",
    ]
    assert event is not None
    assert event.payload == {"value": 1}
    assert event.attention == "mention_later"
    delivery = delivery_store.get(UUID(event_id), "backup-test")
    assert delivery is not None
    assert delivery.status == "succeeded"
    assert delivery.attempts == 1
    source_checkpoint = source_checkpoint_store.get("backup.source")
    assert source_checkpoint is not None
    assert source_checkpoint.cursor == "cursor-1"
    assert source_checkpoint.observations_published == 1
    restored_service_run = service_run_store.latest()
    assert restored_service_run is not None
    assert restored_service_run.status == "succeeded"
    restored_audit = skill_audit_store.list()
    assert len(restored_audit) == 1
    assert restored_audit[0].skill_id == "backup.skill"
    assert restored_audit[0].status == "succeeded"
    assert not hasattr(restored_audit[0], "result")
    assert schedule is not None
    assert schedule.name == "Synthetic schedule"
    assert schedule.interval_seconds == 300


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

    with pytest.raises(BackupValidationError, match=r"size|SHA-256"):
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
