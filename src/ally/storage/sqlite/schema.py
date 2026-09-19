"""Versioned SQLite schema migrations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        version=1,
        name="conversations",
        statements=(
            """
            CREATE TABLE conversations (
                id TEXT PRIMARY KEY,
                title TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE conversation_messages (
                id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL
                    REFERENCES conversations(id) ON DELETE CASCADE,
                position INTEGER NOT NULL,
                role TEXT NOT NULL
                    CHECK (role IN ('system', 'user', 'assistant', 'tool')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (conversation_id, position)
            )
            """,
            """
            CREATE INDEX idx_conversation_messages_conversation
            ON conversation_messages(conversation_id, position)
            """,
            """
            CREATE INDEX idx_conversations_updated_at
            ON conversations(updated_at DESC)
            """,
        ),
    ),
    Migration(
        version=2,
        name="memory_v1",
        statements=(
            """
            CREATE TABLE memory_records (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL
                    CHECK (
                        kind IN (
                            'episodic',
                            'semantic',
                            'procedural',
                            'preference',
                            'relational'
                        )
                    ),
                content TEXT NOT NULL,
                source_type TEXT NOT NULL
                    CHECK (
                        source_type IN (
                            'user',
                            'conversation',
                            'document',
                            'tool',
                            'system'
                        )
                    ),
                source_id TEXT,
                source_uri TEXT,
                confidence REAL NOT NULL
                    CHECK (confidence >= 0.0 AND confidence <= 1.0),
                importance REAL NOT NULL
                    CHECK (importance >= 0.0 AND importance <= 1.0),
                privacy TEXT NOT NULL
                    CHECK (privacy IN ('private', 'shared', 'public')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                observed_at TEXT,
                valid_from TEXT,
                valid_until TEXT,
                supersedes TEXT REFERENCES memory_records(id),
                superseded_at TEXT,
                superseded_by TEXT REFERENCES memory_records(id),
                retracted_at TEXT
            )
            """,
            """
            CREATE INDEX idx_memory_active
            ON memory_records(superseded_at, retracted_at)
            """,
            """
            CREATE INDEX idx_memory_kind_importance
            ON memory_records(kind, importance DESC)
            """,
            """
            CREATE INDEX idx_memory_validity
            ON memory_records(valid_from, valid_until)
            """,
        ),
    ),
    Migration(
        version=3,
        name="knowledge_v1",
        statements=(
            """
            CREATE TABLE knowledge_sources (
                id TEXT PRIMARY KEY,
                uri TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                media_type TEXT NOT NULL,
                current_revision INTEGER NOT NULL CHECK (current_revision >= 1),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE knowledge_revisions (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL
                    REFERENCES knowledge_sources(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL CHECK (revision >= 1),
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (source_id, revision)
            )
            """,
            """
            CREATE TABLE knowledge_chunks (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL
                    REFERENCES knowledge_sources(id) ON DELETE CASCADE,
                revision_id TEXT NOT NULL
                    REFERENCES knowledge_revisions(id) ON DELETE CASCADE,
                revision INTEGER NOT NULL CHECK (revision >= 1),
                ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                content TEXT NOT NULL,
                start_char INTEGER NOT NULL CHECK (start_char >= 0),
                end_char INTEGER NOT NULL CHECK (end_char > start_char),
                sha256 TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE (revision_id, ordinal)
            )
            """,
            """
            CREATE INDEX idx_knowledge_revisions_source
            ON knowledge_revisions(source_id, revision DESC)
            """,
            """
            CREATE INDEX idx_knowledge_chunks_revision
            ON knowledge_chunks(revision_id, ordinal)
            """,
            """
            CREATE INDEX idx_knowledge_sources_updated
            ON knowledge_sources(updated_at DESC)
            """,
        ),
    ),
    Migration(
        version=4,
        name="tool_audit",
        statements=(
            """
            CREATE TABLE tool_audit_records (
                id TEXT PRIMARY KEY,
                invocation_id TEXT NOT NULL,
                tool_name TEXT NOT NULL,
                risk TEXT
                    CHECK (
                        risk IS NULL OR risk IN (
                            'read_only',
                            'reversible',
                            'external_consequence',
                            'high_consequence'
                        )
                    ),
                decision TEXT
                    CHECK (
                        decision IS NULL OR decision IN (
                            'allow',
                            'require_approval',
                            'deny'
                        )
                    ),
                status TEXT NOT NULL
                    CHECK (
                        status IN (
                            'succeeded',
                            'approval_required',
                            'denied',
                            'failed'
                        )
                    ),
                arguments_json TEXT NOT NULL,
                output_json TEXT,
                error TEXT,
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX idx_tool_audit_started
            ON tool_audit_records(started_at DESC)
            """,
            """
            CREATE INDEX idx_tool_audit_invocation
            ON tool_audit_records(invocation_id)
            """,
        ),
    ),
    Migration(
        version=5,
        name="tasks_v1",
        statements=(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (
                        status IN (
                            'pending',
                            'running',
                            'waiting_approval',
                            'succeeded',
                            'failed',
                            'cancelled'
                        )
                    ),
                failure TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE task_steps (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL
                    REFERENCES tasks(id) ON DELETE CASCADE,
                position INTEGER NOT NULL CHECK (position >= 0),
                tool_name TEXT NOT NULL,
                arguments_json TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (
                        status IN (
                            'pending',
                            'running',
                            'approval_required',
                            'succeeded',
                            'failed'
                        )
                    ),
                attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
                last_output_json TEXT,
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (task_id, position)
            )
            """,
            """
            CREATE INDEX idx_tasks_updated
            ON tasks(updated_at DESC)
            """,
            """
            CREATE INDEX idx_task_steps_task
            ON task_steps(task_id, position)
            """,
        ),
    ),
    Migration(
        version=6,
        name="events_v1",
        statements=(
            """
            CREATE TABLE event_records (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                source TEXT NOT NULL,
                importance TEXT NOT NULL
                    CHECK (
                        importance IN (
                            'noise',
                            'routine',
                            'important',
                            'urgent',
                            'critical'
                        )
                    ),
                attention TEXT NOT NULL
                    CHECK (
                        attention IN (
                            'ignore',
                            'remember',
                            'mention_later',
                            'notify',
                            'interrupt',
                            'act'
                        )
                    ),
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                handled_at TEXT
            )
            """,
            """
            CREATE INDEX idx_events_created
            ON event_records(created_at DESC)
            """,
            """
            CREATE INDEX idx_events_attention_handled
            ON event_records(attention, handled_at, created_at DESC)
            """,
            """
            CREATE INDEX idx_events_type_created
            ON event_records(type, created_at DESC)
            """,
        ),
    ),
    Migration(
        version=7,
        name="scheduler_v1",
        statements=(
            """
            ALTER TABLE event_records
            ADD COLUMN dedupe_key TEXT
            """,
            """
            CREATE UNIQUE INDEX idx_events_dedupe_key
            ON event_records(dedupe_key)
            WHERE dedupe_key IS NOT NULL
            """,
            """
            CREATE TABLE schedules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                event_type TEXT NOT NULL,
                importance TEXT NOT NULL
                    CHECK (
                        importance IN (
                            'noise',
                            'routine',
                            'important',
                            'urgent',
                            'critical'
                        )
                    ),
                payload_json TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                interval_seconds INTEGER
                    CHECK (
                        interval_seconds IS NULL
                        OR interval_seconds >= 1
                    ),
                next_run_at TEXT,
                last_run_at TEXT,
                enabled INTEGER NOT NULL
                    CHECK (enabled IN (0, 1)),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX idx_schedules_due
            ON schedules(enabled, next_run_at)
            """,
            """
            CREATE INDEX idx_schedules_updated
            ON schedules(updated_at DESC)
            """,
        ),
    ),
    Migration(
        version=8,
        name="attention_delivery_v1",
        statements=(
            """
            CREATE TABLE attention_deliveries (
                id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL
                    REFERENCES event_records(id) ON DELETE CASCADE,
                sink_id TEXT NOT NULL,
                status TEXT NOT NULL
                    CHECK (status IN ('succeeded', 'failed')),
                attempts INTEGER NOT NULL
                    CHECK (attempts >= 1),
                last_error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                delivered_at TEXT,
                UNIQUE (event_id, sink_id)
            )
            """,
            """
            CREATE INDEX idx_attention_deliveries_status
            ON attention_deliveries(status, updated_at DESC)
            """,
            """
            CREATE INDEX idx_attention_deliveries_event
            ON attention_deliveries(event_id)
            """,
        ),
    ),
    Migration(
        version=9,
        name="event_source_checkpoints_v1",
        statements=(
            """
            CREATE TABLE event_source_checkpoints (
                source_id TEXT PRIMARY KEY,
                cursor TEXT,
                successful_polls INTEGER NOT NULL
                    CHECK (successful_polls >= 1),
                observations_published INTEGER NOT NULL
                    CHECK (observations_published >= 0),
                last_polled_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
            """
            CREATE INDEX idx_event_source_checkpoints_updated
            ON event_source_checkpoints(updated_at DESC)
            """,
        ),
    ),
    Migration(
        version=10,
        name="service_cycle_runs_v1",
        statements=(
            """
            CREATE TABLE service_cycle_runs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL
                    CHECK (
                        status IN (
                            'running',
                            'succeeded',
                            'degraded',
                            'failed',
                            'interrupted'
                        )
                    ),
                observed_at TEXT NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                scheduled_events INTEGER NOT NULL DEFAULT 0
                    CHECK (scheduled_events >= 0),
                delivery_attempts INTEGER NOT NULL DEFAULT 0
                    CHECK (delivery_attempts >= 0),
                delivery_failures INTEGER NOT NULL DEFAULT 0
                    CHECK (
                        delivery_failures >= 0
                        AND delivery_failures <= delivery_attempts
                    ),
                error_class TEXT
                    CHECK (
                        error_class IS NULL
                        OR length(error_class) <= 256
                    ),
                CHECK (
                    (
                        status = 'running'
                        AND finished_at IS NULL
                        AND error_class IS NULL
                    )
                    OR (
                        status IN ('succeeded', 'degraded')
                        AND finished_at IS NOT NULL
                        AND error_class IS NULL
                    )
                    OR (
                        status IN ('failed', 'interrupted')
                        AND finished_at IS NOT NULL
                        AND error_class IS NOT NULL
                    )
                ),
                CHECK (
                    status != 'succeeded'
                    OR delivery_failures = 0
                ),
                CHECK (
                    status != 'degraded'
                    OR delivery_failures >= 1
                )
            )
            """,
            """
            CREATE UNIQUE INDEX idx_service_cycle_single_running
            ON service_cycle_runs(status)
            WHERE status = 'running'
            """,
            """
            CREATE INDEX idx_service_cycle_started
            ON service_cycle_runs(started_at DESC)
            """,
            """
            CREATE INDEX idx_service_cycle_status_started
            ON service_cycle_runs(status, started_at DESC)
            """,
        ),
    ),
)
